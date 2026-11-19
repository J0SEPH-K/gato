# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'chat.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-07-15 08:35:10 UTC (1784104510)

_CHO = ['r', 'R', 's', 'e', 'E', 'f', 'a', 'q', 'Q', 't', 'T', 'd', 'w', 'W', 'c', 'z', 'x', 'v', 'g']
_JUNG = ['k', 'o', 'i', 'O', 'j', 'p', 'u', 'P', 'h', 'hk', 'ho', 'hl', 'y', 'n', 'nj', 'np', 'nl', 'b', 'm', 'ml', 'l']
_JONG = ['', 'r', 'R', 'rt', 's', 'sw', 'sg', 'e', 'f', 'fr', 'fa', 'fq', 'ft', 'fx', 'fv', 'fg', 'a', 'q', 'qt', 't', 'T', 'd', 'w', 'c', 'z', 'x', 'v', 'g']
_JAMO = {'ㄱ': 'r', 'ㄲ': 'R', 'ㄳ': 'rt', 'ㄴ': 's', 'ㄵ': 'sw', 'ㄶ': 'sg', 'ㄷ': 'e', 'ㄸ': 'E', 'ㄹ': 'f', 'ㄺ': 'fr', 'ㄻ': 'fa', 'ㄼ': 'fq', 'ㄽ': 'ft', 'ㄾ': 'fx', 'ㄿ': 'fv', 'ㅀ': 'fg', 'ㅁ': 'a', 'ㅂ': 'q', 'ㅃ': 'Q', 'ㅄ': 'qt', 'ㅅ': 't', 'ㅆ': 'T', 'ㅇ': 'd', 'ㅈ': 'w', 'ㅉ': 'W', 'ㅊ': 'c', 'ㅋ': 'z', 'ㅌ': 'x', 'ㅍ': 'v', 'ㅎ': 'g', 'ㅏ': 'k', 'ㅐ': 'o', 'ㅑ': 'i', 'ㅒ': 'O', 'ㅓ': 'j', 'ㅔ': 'p', 'ㅕ': 'u', 'ㅖ': 'P', 'ㅗ': 'h', 'ㅘ': 'hk', 'ㅙ': 'ho', 'ㅚ': 'hl', 'ㅛ': 'y', 'ㅜ': 'n', 'ㅝ': 'nj', 'ㅞ': 'np', 'ㅟ': 'nl', 'ㅠ': 'b', 'ㅡ': 'm', 'ㅢ': 'ml', 'ㅣ': 'l'}
_SYMBOLS = {'!': (True, '1'), '@': (True, '2'), '#': (True, '3'), '$': (True, '4'), '%': (True, '5'), '^': (True, '6'), '&': (True, '7'), '*': (True, '8'), '(': (True, '9'), ')': (True, '0'), '-': (False, 189), '_': (True, 189), '=': (False, 187), '+': (True, 187), '[': (False, 219), '{': (True, 219), ']': (False, 221), '}': (True, 221), '\\': (False, 220), '|': (True, 220), ';': (False, 186), ':': (True, 186), "'": (False, 222), '"': (True, 222), ',': (False, 188), '<': (True, 188), '.': (False, 190), '>': (True, 190), '/': (False, 191), '?': (True, 191), '`': (False, 192), '~': (True, 192)}
def filter_text(s: str) -> str:
    return ''.join((ch for ch in s or '' if ch == ' ' or ch.isdigit() or 44032 <= ord(ch) <= 55203 or (ch in _JAMO) or (ch in _SYMBOLS))).strip()
def to_tokens(text: str) -> list:
    # irreducible cflow, using cdg fallback
    # ***<module>.to_tokens: Failure: Different control flow
    tokens = []
    def emit(qwerty: str):
        for c in qwerty:
            if c.isupper():
                tokens.append((True, c.lower()))
            else:
                tokens.append((False, c))
    for ch in text or '':
        code = ord(ch)
        if ch == ' ':
            tokens.append((False, 'space'))
            if ch.isdigit():
                tokens.append((False, ch))
                if 44032 <= code <= 55203:
                        s = code - 44032
                        emit(_CHO[s // 588] + _JUNG[s % 588 // 28] + _JONG[s % 28])
                        if ch in _JAMO:
                            emit(_JAMO[ch])
                        else:
                            if ch in _SYMBOLS:
                                tokens.append(_SYMBOLS[ch])
    return tokens