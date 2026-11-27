# 조철 — packet route and the client objects that back it

Written after the RTTI/COL wall was finally broken (the PE header of the packed
client has `SizeOfOptionalHeader = 0x1000`, not the usual `0xf0`, and Themida
blanks every section name to spaces — any section walk that assumes the normal
header reads garbage and every lookup silently returns zero).

## Why packets and not vision

The server owns the shuffle. The client is only told the result, so the swap
sequence and the final holder are in the port-8000 stream. Vision has been
measured and lost: 0/6 for the 15 fps macro, 1/6 and 0-1/6 for two
tracking-by-detection prototypes, 0-1/4 for MOG2+Norfair across 32 settings
(see JOCHUL_FINDINGS.md). The medallion does reappear over the true holder, but
only near the end, and the answer timer is 10 s — one burst read is not enough
to be sure, and a miss costs an escalating account-wide penalty.

## Framing

Chat on 4011 is `u16 LE length | u16 LE opcode`. The main socket is expected to
match. `pktjochul` does not assume it: it scores both endiannesses on how much
of the stream actually tiles into frames and takes the winner. Random u16 values
almost never chain, so the wrong endianness scores near 0 %.

## Decoder contract (abstain-first)

- `MIN_PAIR_RATE = 0.80`, `MIN_SWAPS = 3`: an opcode only counts as the swap
  opcode if at least 80 % of its frames decode to a slot pair and it appears at
  least three times.
- Exactly one surviving opcode, otherwise abstain. Two plausible opcodes means
  the layout is ambiguous and mixing them corrupts the permutation.
- If two survive, rank on pair *variety* (a real swap opcode moves different
  characters) and still abstain on a tie.
- `solve()` returns `None`, never a guess, when the stream does not decode into
  a permutation that still contains the start slot.

`dev/test_pktjochul.py` covers 13 cases: LE and BE tiling, opcode gating, both
abstain paths, retransmit dedupe, client-pick read, clean `begin()`. All pass.

## Offline replay

`probe/replay.py` decides a saved round after the fact and is the only way to
fix an abstain, because the stream is gone the moment the round ends:

    python3 probe/replay.py scan   <dump>          framing %, opcode histogram, pair rates
    python3 probe/replay.py frames <dump> <opcode> every frame of one opcode, body decoded
    python3 probe/replay.py solve  <dump> <start>  the answer the stream implies, or why not

It reads both `pktjochul.dump()` output and the sniffer's raw dump format.
`brain._handle_jochul_inner` always dumps the round's segments to
`debug/jochul_pkts/` before solving, so an abstaining round stays replayable.

## Client objects (for the memory-read cross-check)

Real RVAs from the unpacked client, image base `0x7ff779bc0000`:

| class | COL | vftable |
|---|---|---|
| `CSecretInspector_Parser` | `0x1182988` | `0xb63808` |
| `CQuestionState` | `0x1177740` | `0xb32e80` |
| `CPrepareQuestionState` | `0x11776c0` | `0xb32e50` |
| `ContentSecretInspector` | `0x1160a88` | `0xb16ef8` |

`ContentSecretInspector` is the board/UI object: its vtable slots 0-2 and 20
reference `UI\SecretInspector.json`, `SecretInspector`, `NumberRed`,
`NoticeText1`. Slot 3 is the countdown tick — it reads `[rcx+0x50]` (a `u16`
slot index) into an object array at `[rcx+0x38]`, calls `[rax+0x10]` per entry,
then converts the remaining time to a two-digit label (thresholds `0x2710` /
`0xbb8`). Slot 20 is the state change that loads the `SecretInspector` UI scene.

`CSecretInspector_Parser` slot 0 loads `CharSecondImpact.txt` into a vector
whose index helper is `imul r9, 0x110` — a fixed 0x110-byte record. The push
path at `0x9737d0` memcpy's one record and compares fields `+0x68 / +0x70 /
+0x74 / +0x78` before accepting it. That stride is what a memory reader needs
instead of guessed offsets.

## Open

- No live capture has been taken yet, so the frame layout and the swap opcode
  are still unvalidated against real traffic.
- The relay queue and the LAN fallback were both dead at the time of writing
  (see below), which is the current blocker for that capture.

## Relay / LAN status at time of writing

- Worker relay: 7 queued jobs for `qwer`, all at 0 bytes, never picked up;
  `qwer`'s last `/agent/poll` is ~3 h old while the app last reported
  `uptime_s` 843 and `running: true`, i.e. the loop stopped after its first
  post.
- LAN fallback: `192.168.0.2` does not answer from the Mac (host is
  `192.168.0.148`, `192.168.0.3`/`.50` open nothing), and the PC's agent token
  (`mt4hjwtg…`) does not match the Mac LAN server's token (`dd6506aa…`), so
  every poll returns `{"error":"bad token"}`.
- `~/.gato_hub/state.json` holds a stale quick-tunnel URL for `qwer`
  (`image-soma-contribute-forgotten.trycloudflare.com`) that no longer resolves.
