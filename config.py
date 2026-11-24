# Source Generated with Decompyle++
# File: config.pyc (Python 3.11)

from __future__ import annotations
import copy
import hashlib
import json
import logging
import math
import os
import tempfile
import threading
RES_DIR = os.path.dirname(os.path.abspath(__file__))   # read-only program files (assets, models, ui)
if getattr(__import__('sys'), 'frozen', False):
    # Installed app (Program Files is not writable): settings, logs and debug frames go to a user dir
    BASE_DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'GATO')
    os.makedirs(BASE_DIR, exist_ok=True)
else:
    BASE_DIR = RES_DIR
SETTINGS_PATH = os.path.join(BASE_DIR, 'prism_settings.json')


def _version_candidates():
    # A file literally named VERSION next to the exe shadows the system
    # C:\Windows\System32\version.dll on case-insensitive NTFS, so anything
    # asking for VERSION.dll there gets a 7-byte text file instead of a PE image.
    # Ship it under res/ instead.
    return (os.path.join(RES_DIR, 'res', 'VERSION'),
            os.path.join(RES_DIR, 'VERSION'),
            os.path.join(BASE_DIR, 'VERSION'))


def read_version() -> str:
    """Best-effort app version; '' when nothing readable is found."""
    for p in _version_candidates():
        try:
            with open(p, encoding='utf-8') as f:
                v = f.read().strip()
        except Exception:
            continue
        if v and v[0].isdigit():
            return v
    return ''

MODEL_DIR = os.path.join(RES_DIR, 'assets', 'models', 'monster')
PORTRAIT_DIR = os.path.join(RES_DIR, 'assets', 'imgs', 'monster')
JOCHUL_MODEL = os.path.join(RES_DIR, 'assets', 'models', 'jochul', 'jochul.pt')
TEXT_MODEL = os.path.join(RES_DIR, 'assets', 'models', 'text', 'best.pth')
BATTLE_DEBUG_DIR = os.path.join(BASE_DIR, 'debug', 'battle')
DIGIT_DEBUG_DIR = os.path.join(BASE_DIR, 'debug', 'digits')
AIM_DEBUG_DIR = os.path.join(BASE_DIR, 'debug', 'aim')
JOCHUL_FAIL_DIR = os.path.join(BASE_DIR, 'debug', 'jochul_fail')
JAMUN_DIR = os.path.join(BASE_DIR, 'debug', 'jamun')
PACKET_DUMP_DIR = os.path.join(BASE_DIR, 'debug', 'packets')
SIG_AUDIT_DIR = os.path.join(BASE_DIR, 'debug', 'sig_audit')
BATTLE_SKIP_DIR = os.path.join(BASE_DIR, 'debug', 'battle_skip')
PAN_DEBUG_DIR = os.path.join(BASE_DIR, 'debug', 'pan')
BATTLE_COUNT_PATH = os.path.join(BASE_DIR, 'battle_count.txt')
APPEAR_PATH = os.path.join(BASE_DIR, 'appear_records.txt')
DEFAULT_MONSTER = '암령의시녀'
MOB_CATEGORIES = [
    '악몽(틈/근원)',
    '신선곡',
    '광려산/환상계곡',
    '샴발라(천옥/관문)',
    '기타']
MOB_CATALOG = {
    '암령의시녀': {
        'model': 'best_mob_sogm.pt',
        'conf': 0.9,
        'aim_y': 0,
        'portrait': 'sogm.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.7,
            20],
        'avoid_conf': 0.8,
        'pan_dist': 0.3,
        'sprite': [
            'dark_gujimo_maid_n',
            'dark_gujimo_maid_m'],
        'fire_rect': [
            0.22,
            0.49,
            0.78,
            0.83],
        'category': '광려산/환상계곡' },
    '암령의사육사': {
        'model': 'best_mob_sogm2.pt',
        'conf': 0.9,
        'aim_y': 0,
        'portrait': 'sogm2.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            20],
        'avoid_conf': 0.8,
        'pan_dist': 0.3,
        'sprite': [
            'dark_gujimo_keeper_n',
            'dark_gujimo_keeper_m'],
        'fire_rect': [
            0.19,
            0.58,
            0.81,
            0.92],
        'category': '광려산/환상계곡' },
    '암령의고주': {
        'model': 'best_mob_sogm3.pt',
        'conf': 0.9,
        'aim_y': 0,
        'portrait': 'sogm3.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.9,
            20],
        'avoid_conf': 0.8,
        'pan_dist': 0.3,
        'sprite': [
            'dark_gujimo_employer_n',
            'dark_gujimo_employer_m'],
        'fire_rect': [
            0.22,
            0.58,
            0.78,
            0.92],
        'category': '광려산/환상계곡' },
    '암령의장로': {
        'model': 'best_mob_sogm4.pt',
        'conf': 0.9,
        'aim_y': 0,
        'portrait': 'sogm4.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.82,
            28],
        'avoid_conf': 0.8,
        'pan_dist': 0.3,
        'sprite': [
            'dark_gujimo_elder_n',
            'dark_gujimo_elder_m'],
        'fire_rect': [
            0.19,
            0.55,
            0.81,
            0.95],
        'category': '광려산/환상계곡' },
    '두이': {
        'model': 'best_mob_dui.pt',
        'conf': 0.85,
        'aim_y': 0,
        'portrait': 'dui.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.9,
            28],
        'avoid_conf': 0.85,
        'pan_dist': 0.3,
        'sprite': [
            'dui'],
        'fire_rect': [
            0.16,
            0.58,
            0.84,
            0.92],
        'category': '기타' },
    '궁_교룡': {
        'projection_scale': [
            26.7,
            26.1],
        'model': 'best_mob_gyo_w.pt',
        'conf': 0.9,
        'aim_y': 0,
        'portrait': 'gyo_w.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'avoid_conf': 0.9,
        'pan_dist': 0.65,
        'fire_rect': [
            0.28,
            0.58,
            0.72,
            0.92],
        'lead_angle': True,
        'category': '샴발라(천옥/관문)' },
    '도사_허': {
        'model': 'best_mob_dosa_heo.pt',
        'conf': 0.85,
        'aim_y': 0,
        'portrait': 'dosa_heo.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.96,
            64],
        'avoid_conf': 0.85,
        'trust_avoid': True,
        'pan_dist': 0.35,
        'sprite': [
            'master_heo_n',
            'master_heo_m'],
        'fire_rect': [
            0.34,
            0.85,
            0.66,
            1.19],
        'category': '광려산/환상계곡' },
    '너구리': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.3,
        'sprite': [
            'raccoondog_online'],
        'category': '기타' },
    '건달바의혼': {
        'model': 'best_mob_gun.pt',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'gun.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.9,
            28],
        'avoid_conf': 0.8,
        'sprite': [
            'gundaba'],
        'fire_rect': [
            0.07,
            0.55,
            0.93,
            0.95],
        'category': '신선곡' },
    '오운_전': {
        'model': 'best_mob_oun_jeon.pt',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'oun_jeon.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.9,
            30],
        'avoid_conf': 0.9,
        'sprite': [
            'lord_koyang_n',
            'lord_koyang_m'],
        'fire_rect': [
            0.19,
            0.55,
            0.81,
            0.95],
        'category': '기타' },
    '삼미호': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'sammi.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'sammiho_t'],
        'fire_rect': [
            0.28,
            0.64,
            0.72,
            0.86],
        'category': '신선곡' },
    '거북궁사': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'tman.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'tuttleman'],
        'fire_rect': [
            0.28,
            0.61,
            0.72,
            0.89],
        'category': '기타',
        'ignore_dummy': True },
    '신장_경문': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.6,
        'portrait': 'gyeongmun_f.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'gyeongmun_f_n',
            'gyeongmun_f_m'],
        'boss': True,
        'boss_conf': 0.55,
        'fire_rect': [
            0.28,
            0.88,
            0.72,
            0.98],
        'category': '샴발라(천옥/관문)',
        'pan_ratio': 1 },
    '도사_귀': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_gui.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_gui_n',
            'master_gui_m'],
        'fire_rect': [
            0.19,
            0.76,
            0.81,
            0.98],
        'category': '광려산/환상계곡' },
    '도사_각': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_gak.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_gak_n',
            'master_gak_m'],
        'fire_rect': [
            0.31,
            0.85,
            0.69,
            1.13],
        'category': '광려산/환상계곡' },
    '도사_삼': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_sam.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_sam_n',
            'master_sam_m'],
        'fire_rect': [
            0.31,
            0.85,
            0.69,
            1.13],
        'category': '광려산/환상계곡' },
    '악몽귀': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'acmong.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'acmong_gui_n',
            'acmong_gui_r'],
        'fire_rect': [
            0.22,
            0.82,
            0.78,
            0.98],
        'category': '악몽(틈/근원)' },
    '아디티': {
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'aditi.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'aditi'],
        'fire_rect': [
            0.25,
            0.73,
            0.75,
            0.95],
        'category': '신선곡' },
    '수룡': {
        'model': 'best_mob_water_dragon.pt',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'water_dragon.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'avoid_conf': 0.7,
        'fire_rect': [
            0.4,
            0.82,
            0.6,
            1.1],
        'category': '기타' },
    '잠식귀(수)': {
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'jam_w.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'jamsic_w_n',
            'jamsic_w_m'],
        'fire_rect': [
            0.22,
            0.79,
            0.78,
            1.01],
        'category': '악몽(틈/근원)' },
    '잠식귀(풍)': {
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'jam_a.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'jamsic_a_n',
            'jamsic_a_r'],
        'fire_rect': [
            0.34,
            0.7,
            0.66,
            0.92],
        'category': '악몽(틈/근원)' },
    '잠식귀(화)': {
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'jam_f.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'jamsic_f_n',
            'jamsic_f_m'],
        'fire_rect': [
            0.22,
            0.64,
            0.78,
            0.86],
        'category': '악몽(틈/근원)' },
    '잠식귀(뇌)': {
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'jam_t.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'jamsic_t_n',
            'jamsic_t_r'],
        'fire_rect': [
            0.19,
            0.64,
            0.81,
            0.86],
        'category': '악몽(틈/근원)' },
    '구지모시녀장': {
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'gusi.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'guzimo_sister'],
        'fire_rect': [
            0.25,
            0.67,
            0.75,
            0.95],
        'category': '기타' },
    '궁_미후': {
        'projection_scale': [
            26.7,
            26.1],
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.65,
        'portrait': 'mihu_f.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'mihu_f_n',
            'mihu_f_m'],
        'fire_rect': [
            0.28,
            0.7,
            0.72,
            0.92] },
    '궁_대호': {
        'projection_scale': [
            26.7,
            26.1],
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.65,
        'portrait': 'daeho_t.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'daeho_t_n',
            'daeho_t_m'],
        'fire_rect': [
            0.34,
            0.7,
            0.66,
            0.98] },
    '궁_흉맥': {
        'projection_scale': [
            26.7,
            26.1],
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.65,
        'portrait': 'hyungmaek_a.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'hyungmaek_a_n',
            'hyungmaek_a_m'],
        'fire_rect': [
            0.34,
            0.61,
            0.66,
            0.89] },
    '악령_수령': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'ghostsr.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'ghostsr_n',
            'ghostsr_m'],
        'fire_rect': [
            0.31,
            0.91,
            0.69,
            1.07] },
    '악령_염옥': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'ghostyo.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'ghostyo_n',
            'ghostyo_m'],
        'fire_rect': [
            0.4,
            0.67,
            0.6,
            0.77] },
    '구지모사역술사': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.3,
        'portrait': 'gusa.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'gujimo_spiritualist_n',
            'gujimo_spiritualist_r'],
        'fire_rect': [
            0.25,
            0.52,
            0.75,
            0.68] },
    '연옥동자': {
        'category': '신선곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'yeonok.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'devilfirem_s'],
        'fire_rect': [
            0.31,
            0.82,
            0.69,
            1.1] },
    '마후라가의혼': {
        'category': '신선곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'mahu.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'mahuraga'],
        'fire_rect': [
            0.28,
            0.88,
            0.72,
            1.04] },
    '누에': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'nue.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'nue'],
        'fire_rect': [
            0.37,
            0.67,
            0.63,
            0.83] },
    '석사자': {
        'category': '기타',
        'model': 'best_mob_stone_l.pt',
        'conf': 0.85,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'suksa.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'fire_rect': [
            0.16,
            0.64,
            0.84,
            0.92] },
    '기': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'kui.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'kui'],
        'fire_rect': [
            0.34,
            0.76,
            0.66,
            0.98] },
    '염라대왕': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'hellking.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'hellking'],
        'fire_rect': [
            0.22,
            0.76,
            0.78,
            0.92] },
    '유물지도': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.4,
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'ruins_guardian_n',
            'ruins_guardian_m'],
        'fire_rect': [
            0.31,
            0.67,
            0.69,
            0.95],
        'box_click': True,
        'ignore_weight': True,
        'ignore_teleport': True,
        'ignore_dummy': True,
        'portrait': 'yumul.PNG' },
    '유물지도(정예)': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': -20,
        'pan_dist': 0.4,
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'elite_ruins_guardian_n',
            'elite_ruins_guardian_m'],
        'fire_rect': [
            0.34,
            0.76,
            0.66,
            0.98],
        'box_click': True,
        'ignore_weight': True,
        'ignore_teleport': True,
        'ignore_dummy': True,
        'portrait': 'yumul_e.PNG' },
    '늪지이무기': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'swamphydra.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'swamphydra'] },
    '귀_염우': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.55,
        'portrait': 'fiend_thunder.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'thunder_fiend_n',
            'thunder_fiend_m'],
        'fire_rect': [
            0.43,
            0.73,
            0.57,
            0.83],
        'pan_ratio': 1 },
    '신장_사문': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.6,
        'portrait': 'samun.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'samun_t_n',
            'samun_t_m'],
        'fire_rect': [
            0.34,
            0.82,
            0.66,
            0.98],
        'pan_ratio': 1 },
    '공작원_다령': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dr_op.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'operative_dr_n',
            'operative_dr_m'],
        'fire_rect': [
            0.34,
            0.64,
            0.66,
            0.86] },
    '현진_장로': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'hj_elder.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'hj_elder_n',
            'hj_elder_m'],
        'fire_rect': [
            0.37,
            0.67,
            0.63,
            0.89] },
    '벼락의 사령술사': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'bss.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'lightning_magicofflcer_n',
            'lightning_magicofflcer_m'],
        'fire_rect': [
            0.28,
            0.64,
            0.72,
            0.86] },
    '궁_사수': {
        'projection_scale': [
            26.7,
            26.1],
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.65,
        'portrait': 'sasu.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'sasu_t_n',
            'sasu_t_m'],
        'fire_rect': [
            0.34,
            0.61,
            0.66,
            0.83] },
    '복수자_샤오링': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'r_sha.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'revenger_shaoring_n',
            'revenger_shaoring_m'],
        'fire_rect': [
            0.28,
            0.79,
            0.72,
            0.95] },
    '루드라의혼': {
        'category': '신선곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'rudra.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'rudra'],
        'fire_rect': [
            0.28,
            0.55,
            0.72,
            0.77] },
    '백면구미호': {
        'category': '신선곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'bg.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'ninetailedfox_s_n',
            'ninetailedfox_s_r'],
        'fire_rect': [
            0.34,
            0.73,
            0.66,
            0.89] },
    '귀_투적': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.55,
        'portrait': 'fiend_crimson.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'pan_ratio': 1,
        'sprite': [
            'crimson_fiend_n',
            'crimson_fiend_m'],
        'fire_rect': [
            0.34,
            0.82,
            0.66,
            1.04] },
    '지식의고룡': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.75,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'know.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'knowledged_n',
            'knowledged_m'],
        'fire_rect': [
            0.34,
            0.73,
            0.66,
            0.89] },
    '실험체발로': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.75,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'balo.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'subject_balro_n',
            'subject_balro_r'],
        'fire_rect': [
            0.34,
            0.7,
            0.66,
            0.98] },
    '욕수의사념': {
        'category': '기타',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'yoksu.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'yoksu'],
        'fire_rect': [
            0.25,
            0.85,
            0.75,
            1.07] },
    '도사_저': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_jeo.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_jeo_n',
            'master_jeo_m'],
        'fire_rect': [
            0.34,
            0.73,
            0.66,
            0.95] },
    '오운_태': {
        'category': '기타',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'oun_tae.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'lord_bokhee_n',
            'lord_bokhee_m'],
        'fire_rect': [
            0.4,
            0.7,
            0.6,
            0.8] },
    '도사_성': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_sung.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_sung_n',
            'master_sung_m'],
        'fire_rect': [
            0.37,
            0.85,
            0.63,
            1.13] },
    '신장_휴문': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.6,
        'portrait': 'hyumun.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'hyumun_t_n',
            'hyumun_t_m'],
        'fire_rect': [
            0.37,
            0.79,
            0.63,
            1.01],
        'pan_ratio': 1 },
    '신장_생문': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.9,
        'aim_y': 0,
        'pan_dist': 0.6,
        'portrait': 'saengmun.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'pan_ratio': 1,
        'sprite': [
            'saengmun_a_n',
            'saengmun_a_m'],
        'fire_rect': [
            0.34,
            0.79,
            0.66,
            1.01] },
    '악몽지기': {
        'category': '악몽(틈/근원)',
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'acmonggui.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'dark_guardian_n',
            'dark_guardian_r'],
        'fire_rect': [
            0.37,
            0.7,
            0.63,
            0.92] },
    '도사_필': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_pil.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_pil_n',
            'master_pil_m'],
        'fire_rect': [
            0.34,
            0.79,
            0.66,
            1.01] },
    '악령_전이': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'ghostjy.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'ghostjy_n',
            'ghostjy_m'],
        'fire_rect': [
            0.34,
            0.64,
            0.66,
            0.86] },
    '도사_여': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'dosa_yeo.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'master_yeo_n',
            'master_yeo_m'],
        'fire_rect': [
            0.28,
            0.58,
            0.72,
            0.8] },
    '제사장_허독': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'fo_hd.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'pontifex_hd_n',
            'pontifex_hd_m'],
        'fire_rect': [
            0.34,
            0.64,
            0.66,
            0.86] },
    '천옥_천망수': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.8,
        'aim_y': 0,
        'pan_dist': 0.65,
        'portrait': 'cheonmang.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'cheonmang_n',
            'cheonmang_m'],
        'fire_rect': [
            0.28,
            0.88,
            0.72,
            1.1],
        'projection_scale': [
            26,
            26] },
    '악령_풍마': {
        'category': '광려산/환상계곡',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'ghostpm.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'ghostpm_n',
            'ghostpm_m'],
        'fire_rect': [
            0.34,
            0.64,
            0.66,
            0.8] },
    '천옥_집행수': {
        'category': '샴발라(천옥/관문)',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.65,
        'portrait': 'jiphaeng.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'jiphaeng_n',
            'jiphaeng_m'],
        'fire_rect': [
            0.22,
            0.64,
            0.78,
            0.98],
        'projection_scale': [
            26,
            26] },
    '오운_소': {
        'category': '기타',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'oun_so.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'lord_kumchun_n',
            'lord_kumchun_m'],
        'fire_rect': [
            0.31,
            0.67,
            0.69,
            0.95] },
    '오운_염': {
        'category': '기타',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.4,
        'portrait': 'oun_yum.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'lord_shinnong_n',
            'lord_shinnong_m'],
        'fire_rect': [
            0.25,
            0.67,
            0.75,
            0.95] },
    '백안귀': {
        'category': '신선곡',
        'model': '',
        'conf': 0.7,
        'aim_y': 0,
        'pan_dist': 0.35,
        'portrait': 'devileyes.PNG',
        'fire_filter': True,
        'fire_roi': [
            0.5,
            0.8,
            28],
        'sprite': [
            'devileyes_s'],
        'fire_rect': [
            0.19,
            0.61,
            0.81,
            0.89] } }
DEFAULT_MONSTER_CFG = {
    'squad_counts': [
        2,
        2,
        2,
        2,
        2,
        2],
    'center_move_delay': 1,
    'lead_px': 80,
    'summon_mode': 'none',
    'use_summon': False,
    'multi_retreat': False,
    'noejeonju': False,
    'attack_keys': [
        '3',
        '4',
        '5',
        '6'],
    'travel_mode': 'none',
    'travel_scroll_item': '',
    'travel_waypoints': [] }
DEFAULT_COMMON = {
    'second_password': '',
    'auto_restock_enabled': False,
    'food_item': '삼색채경단',
    'battle_modes': True,
    'prefight_food': True,
    'prefight_revive': True,
    'food_buy_qty': 200,
    'cleanup_sell_items': '',
    'cleanup_keep_items': '',
    'gm_chat_msg': '',
    'discord_webhook': '',
    'discord_token': '',
    'discord_channel': '',
    'ntfy_url': '',
    'link_enabled': True,
    'link_topic': '',
    'link_token': '',
    'ngrok_authtoken': '',
    'notify_whisper': True,
    'notify_normal': False,
    'notify_repeat': False,
    'banja_mode': False,
    'win_w': 960,
    'win_h': 660,
    'sched_cycles': 3,
    'sched_battles': 10,
    'sched_rest_sec': 600 }

def _mob(monster: str) -> dict:
    return MOB_CATALOG.get(monster) or MOB_CATALOG[DEFAULT_MONSTER]


def mob_model_path(monster: str) -> str:
    m = _mob(monster)
    return os.path.join(MODEL_DIR, m['model']) if m.get('model') else ''


def battle_model_path(monster: str) -> str:
    m = _mob(monster)
    return os.path.join(MODEL_DIR, m['battle']) if m.get('battle') else ''


def mob_conf(monster: str) -> float:
    return float(_mob(monster)['conf'])


def battle_conf(monster: str) -> float:
    return float(_mob(monster)['battle_conf'])


def mob_aim_y(monster: str) -> float:
    return float(_mob(monster)['aim_y'])


def mob_aim_y4(monster: str):
    v = _mob(monster).get('aim_y4')
    return [float(x) for x in v] if v else None


def mob_fire_roi(monster: str):
    m = _mob(monster)
    if not m.get('fire_filter', True):
        return None
    return tuple(m.get('fire_roi', [
        0.5,
        0.8,
        28]))


def mob_sprite(monster: str):
    s = _mob(monster).get('sprite')
    return s or None



def mob_fire_rect(monster: str):
    m = _mob(monster)
    r = m.get('fire_rect')
    if r:
        return tuple((float(v) for v in r))
    t = m.get('fire_top')
    if t:
        return (-0.08, float(t), 1.08, 1.1)


def mob_gate_scale(monster: str):
    v = _mob(monster).get('gate_scale')
    return float(v) if v else None


def mob_avoid_conf(monster: str):
    v = _mob(monster).get('avoid_conf')
    return float(v) if v else None


def mob_pan_dist(monster: str) -> float:
    return float(_mob(monster).get('pan_dist', 0.4))


def mob_projection_scale(monster: str):
    return _mob(monster).get('projection_scale')


def mob_pan_ratio(monster: str):
    v = _mob(monster).get('pan_ratio')
    return float(v) if v else None

    return float(v)


def mob_lead_angle(monster: str) -> bool:
    return bool(_mob(monster).get('lead_angle', False))


def mob_boss(monster: str) -> bool:
    return bool(_mob(monster).get('boss', False))


def mob_ignore_dummy(monster: str) -> bool:
    return bool(_mob(monster).get('ignore_dummy', False))


def mob_summon_center(monster: str) -> bool:
    return bool(_mob(monster).get('summon_center', False))


def mob_boss_conf(monster: str) -> float:
    v = _mob(monster).get('boss_conf')
    return float(v) if v else None


def mob_trust_avoid(monster: str):
    v = _mob(monster).get('trust_avoid')
    return bool(v) if v else None


def mob_ignore_weight(monster: str) -> bool:
    return bool(_mob(monster).get('ignore_weight', False))


def mob_ignore_teleport(monster: str) -> bool:
    return bool(_mob(monster).get('ignore_teleport', False))


def mob_box_click(monster: str) -> bool:
    return bool(_mob(monster).get('box_click', False))


def mob_pixel_detect(monster: str) -> bool:
    return _mob(monster).get('detect', '') == 'pixel'


def mob_travel_mode(monster: str) -> str:
    return load()['monsters'].get(monster, {}).get('travel_mode', 'none')


def mob_travel_scroll_item(monster: str) -> str:
    return load()['monsters'].get(monster, {}).get('travel_scroll_item', '')


def mob_travel_waypoints(monster: str) -> list:
    return load()['monsters'].get(monster, {}).get('travel_waypoints', [])


def auto_restock_enabled() -> bool:
    return bool(load().get('auto_restock_enabled', False))


def food_item() -> str:
    return load().get('food_item', '삼색채경단')


def food_buy_qty() -> int:
    return int(load().get('food_buy_qty', 200))


def cleanup_sell_items() -> str:
    return load().get('cleanup_sell_items', '')


def cleanup_keep_items() -> str:
    return load().get('cleanup_keep_items', '')


def second_password() -> str:
    return load().get('second_password', '')


def portrait_path(monster: str) -> str:
    m = MOB_CATALOG.get(monster)
    f = m.get('portrait') if m else ''
    return os.path.join(PORTRAIT_DIR, f) if f else ''

SUMMON_MODES = ('none', 'taunt', 'non_taunt')

def summon_mode(settings: dict) -> str:
    mode = settings.get('summon_mode')
    if isinstance(mode, str) and mode in SUMMON_MODES:
        return mode
    return 'taunt' if settings.get('use_summon') is True else 'none'


def _sync_summon_mode(settings: dict):
    mode = summon_mode(settings)
    settings['summon_mode'] = mode
    settings['use_summon'] = mode != 'none'


def _load_raw() -> dict:
    
    try:
        with open(SETTINGS_PATH, encoding = 'utf-8') as f:
            return json.load(f)
    except Exception:
        return None


_cache_lock = threading.Lock()
_cache: 'dict | None' = None
_cache_mtime: 'float | None' = None

def _settings_mtime():
    
    try:
        return os.path.getmtime(SETTINGS_PATH)
    except OSError:
        return None



def load() -> dict:
    global _cache, _cache_mtime
    mt = _settings_mtime()
    with _cache_lock:
        if _cache and mt and mt == _cache_mtime:
            return copy.deepcopy(_cache)
    s = _load_raw() or {}
    monsters = s.setdefault('monsters', { })
    for name in MOB_CATALOG:
        monsters.setdefault(name, dict(DEFAULT_MONSTER_CFG))
    for mc in monsters.values():
        _sync_summon_mode(mc)
        for k, v in DEFAULT_MONSTER_CFG.items():
            mc.setdefault(k, v)
    s['monsters'] = dict(sorted(monsters.items()))
    for k, v in DEFAULT_COMMON.items():
        s.setdefault(k, v)
    if s.get('current_monster') not in MOB_CATALOG:
        s['current_monster'] = DEFAULT_MONSTER
    with _cache_lock:
        _cache = copy.deepcopy(s)
        _cache_mtime = mt
    return s


def save(s: dict) -> bool:
    global _cache, _cache_mtime
    tmp = None
    
    try:
        saved = copy.deepcopy(s)
        for mc in saved.get('monsters', { }).values():
            _sync_summon_mode(mc)
        data = json.dumps(saved, ensure_ascii = False, indent = 2)
        with _cache_lock:
            with tempfile.NamedTemporaryFile(mode = 'w', encoding = 'utf-8', dir = os.path.dirname(SETTINGS_PATH), prefix = '.prism_settings_', suffix = '.tmp', delete = False) as f:
                tmp = f.name
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, SETTINGS_PATH)
            tmp = None
            _cache = saved
            _cache_mtime = _settings_mtime()
        if tmp:
            
            try:
                os.remove(tmp)
                return True
            except OSError:
                return True

        return True
    except Exception as e:
        logging.getLogger(__name__).warning('설정 저장 실패 (기존 설정 유지): %s', e)
        
        try:
            if tmp:
                
                try:
                    os.remove(tmp)
                    return False
                except OSError:
                    return False

            return False
        except:
            if tmp:
                os.remove(tmp)




def parse_squad_counts(sc) -> list:
    if isinstance(sc, list) and len(sc) == 6:
        
        try:
            return [ max(0, float(v)) for v in sc ]
        except Exception:
            pass

    return list(DEFAULT_MONSTER_CFG['squad_counts'])


class SettingsError(ValueError):
    pass


def _v_num(low, high):
    
    def rule(value, label):
        if isinstance(value, bool):
            raise SettingsError(f'''{label}: 숫자를 입력하세요''')
        
        try:
            out = float(value)
        except (TypeError, ValueError):
            raise SettingsError(f'''{label}: 숫자를 입력하세요''')

        if not (math.isfinite(out) and low <= out <= high):
            raise SettingsError(f'''{label}: {low:g}~{high:g} 범위여야 합니다''')
        return out

    return rule


def _v_bool(value, label):
    if not isinstance(value, bool):
        raise SettingsError(f'''{label}: 참/거짓 값이 필요합니다''')
    return value


def _v_summon_mode(value, label):
    if not isinstance(value, str) or value not in SUMMON_MODES:
        raise SettingsError(f'''{label}: 소환 사용 안 함 / 도발 탱 소환 / 비도발 탱 소환 중 선택하세요''')
    return value


def _v_squad(value, label):
    if not isinstance(value, list) or len(value) != 6:
        raise SettingsError(f'''{label}: 부대 1~6 값 6개가 필요합니다''')
    num = _v_num(0, 60)
    return [ num(v, label) for v in value ]


def _v_attack_keys(value, label):
    import combat
    return combat.normalize_attack_keys(value)


def _v_text(value, label):
    if value is None:
        value = ''
    return str(value).strip()


def _v_int(low, high):
    num = _v_num(low, high)
    
    def rule(value, label):
        return int(round(num(value, label)))

    return rule


def _v_choice(options):
    def rule(value, label):
        if value not in options:
            raise SettingsError(f'''{label}: {' / '.join(options)} 중 선택하세요''')
        return value

    return rule


def _v_waypoints(value, label):
    if not isinstance(value, list):
        raise SettingsError(f'''{label}: 기록된 경로 목록이어야 합니다''')
    out = []
    for step in value:
        if not isinstance(step, dict) or 'x' not in step or 'y' not in step:
            raise SettingsError(f'''{label}: 각 단계는 x, y 좌표가 필요합니다''')
        out.append({
            'x': int(step['x']),
            'y': int(step['y']),
            'wait': float(step.get('wait', 0.0))})
    return out


MONSTER_CFG_RULES = {
    'squad_counts': ('부대별 타격 시간', _v_squad),
    'center_move_delay': ('중앙 이동 대기', _v_num(0, 10)),
    'lead_px': ('선보정', _v_num(0, 300)),
    'summon_mode': ('소환 방식', _v_summon_mode),
    'use_summon': ('소환 사용', _v_bool),
    'multi_retreat': ('다부대 퇴각', _v_bool),
    'noejeonju': ('뇌전주', _v_bool),
    'attack_keys': ('사용 격수', _v_attack_keys),
    'travel_mode': ('이동 방식', _v_choice(['none', 'walk', '육의전', '무투장', 'scroll'])),
    'travel_scroll_item': ('이동 주문서', _v_text),
    'travel_waypoints': ('기록된 이동 경로', _v_waypoints) }
COMMON_RULES = {
    'second_password': ('2차 비밀번호', _v_text),
    'auto_restock_enabled': ('자동 보충 사용', _v_bool),
    'food_item': ('구매할 음식', _v_text),
    'battle_modes': ('전투 시작 시 전투모드·거래차단 자동 켜기', _v_bool),
    'prefight_food': ('전투 전 포만감 1/5 미만이면 궁중 타락죽으로 채우기', _v_bool),
    'prefight_revive': ('전투 전 죽은 용병 있으면 Alt+1, Alt+2로 부활', _v_bool),
    'food_buy_qty': ('음식 구매 수량', _v_int(0, 99999)),
    'cleanup_sell_items': ('정리(판매)할 아이템', _v_text),
    'cleanup_keep_items': ('보관할 아이템(판매 제외)', _v_text),
    'gm_chat_msg': ('영자 응답 문구', _v_text),
    'discord_webhook': ('디스코드 웹훅', _v_text),
    'discord_token': ('디스코드 토큰', _v_text),
    'discord_channel': ('디스코드 채널', _v_text),
    'ntfy_url': ('ntfy URL', _v_text),
    'link_enabled': ('맥 링크 사용', _v_bool),
    'link_topic': ('맥 링크 주제', _v_text),
    'link_token': ('맥 링크 토큰', _v_text),
    'ngrok_authtoken': ('ngrok 토큰', _v_text),
    'notify_whisper': ('귓말 알림', _v_bool),
    'notify_normal': ('일반 채팅 알림', _v_bool),
    'notify_repeat': ('반복 채팅 알림', _v_bool),
    'banja_mode': ('반자사', _v_bool),
    'win_w': ('창 폭', _v_int(200, 10000)),
    'win_h': ('창 높이', _v_int(200, 10000)),
    'sched_cycles': ('스케쥴 사이클', _v_int(1, 999)),
    'sched_battles': ('사이클당 전투', _v_int(1, 9999)),
    'sched_rest_sec': ('휴식 시간', _v_int(0, 86400)) }

def _warn_missing_rules():
    log = logging.getLogger(__name__)
    for what, defaults, rules in (('몹 전투설정', DEFAULT_MONSTER_CFG, MONSTER_CFG_RULES), ('공통 설정', DEFAULT_COMMON, COMMON_RULES)):
        missing = set(defaults) - set(rules)
        if missing:
            log.warning('%s 검증 규칙 누락: %s (값은 보존하되 검증 안 함)', what, ', '.join(sorted(missing)))

_warn_missing_rules()

def _validate(raw, defaults, rules, base, what):
    if not isinstance(raw, dict):
        raise SettingsError(f'''{what} 형식이 올바르지 않습니다''')
    unknown = set(raw) - set(defaults)
    if unknown:
        raise SettingsError(f'''알 수 없는 {what}: ''' + ', '.join(sorted(unknown)))
    merged = dict(defaults)
    if isinstance(base, dict):
        merged.update({ k: v for k, v in base.items() if k in defaults })
    merged.update(raw)
    out = { }
    for key, default in defaults.items():
        rule = rules.get(key)
        value = merged.get(key, default)
        if rule:
            value = rule[1](value, rule[0])
        out[key] = copy.deepcopy(value)
    return out


def validate_monster_cfg(raw, base = None) -> dict:
    if isinstance(base, dict):
        base = dict(base)
        base['summon_mode'] = summon_mode(base)
    if isinstance(raw, dict) and 'summon_mode' not in raw and 'use_summon' in raw:
        raw = dict(raw)
        raw['summon_mode'] = 'taunt' if raw['use_summon'] is True else 'none'
    out = _validate(raw, DEFAULT_MONSTER_CFG, MONSTER_CFG_RULES, base, '전투 설정')
    _sync_summon_mode(out)
    return out


def validate_common(raw, base = None) -> dict:
    return _validate(raw, DEFAULT_COMMON, COMMON_RULES, base, '공통 설정')

STAMP_EXCLUDE = {
    'stamp',
    'win_h',
    'win_w',
    'auth_id',
    'second_password',
    'sched_cycles',
    'sched_battles',
    'sched_rest_sec'}

def settings_stamp(s: dict | None = None) -> str:
    if s is None:
        s = load()
    view = { k: v for k, v in s.items() if k not in STAMP_EXCLUDE }
    blob = json.dumps(view, ensure_ascii = False, sort_keys = True, default = str)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()[:12]

