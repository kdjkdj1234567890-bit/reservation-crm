#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""놓치고 있던 돈을 찾아주는 시스템 1번 — 업종별 온라인 예약 + 고객 관리 시스템 (데모)

청소업체 / 미용실·네일샵 / 이사·용달 — 업종을 고르면 메뉴·용어·가격대와
특화 기능(작업 사진·디자이너 배정·견적 계산)이 바뀌는 특화 버전입니다.
Flask + SQLite, 외부 API/유료 서비스 없이 전부 동작합니다.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservation.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = "dangol-demo-2026"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

SLOTS = ["09:00", "10:00", "11:00", "12:00", "13:00",
         "14:00", "15:00", "16:00", "17:00"]

STATUS_LABEL = {
    "pending": "접수",
    "confirmed": "확정",
    "completed": "완료",
    "cancelled": "취소",
    "noshow": "노쇼",
}

# ---------------- 업종 프리셋 ----------------
INDUSTRIES = {
    "cleaning": {
        "label": "청소업체", "emoji": "🧹",
        "desc": "입주청소 · 정기청소 · 사무실청소",
        "headline": "전화 응대하느라 현장 놓치지 마세요",
        "sub": "손님이 직접 예약하고, 청소 전후 사진으로 실력을 증명하세요.",
        "people": {"unit": "가정", "counter": "곳", "helped": "깨끗해졌어요",
                   "mission": "깨끗한 집에서 시작되는 하루를 만드세요"},
        "services": [
            {"name": "입주 청소", "price": 150000, "duration": 180,
             "desc": "빈집 전체 + 창틀·베란다",
             "price_note": "20평 15만원 · 30평 22만원 · 40평 29만원"},
            {"name": "정기 청소", "price": 90000, "duration": 120,
             "desc": "주 1회 · 격주 방문 관리",
             "price_note": "회당 9만원~ (평수별 상이)"},
            {"name": "사무실 청소", "price": 200000, "duration": 240,
             "desc": "퇴근 후 야간 작업 가능",
             "price_note": "30평 20만원~"},
            {"name": "에어컨 청소", "price": 80000, "duration": 60,
             "desc": "벽걸이 분해 청소",
             "price_note": "대당 8만원"},
        ],
    },
    "beauty": {
        "label": "미용실·네일샵", "emoji": "💇",
        "desc": "커트 · 염색 · 펌 · 네일아트",
        "headline": "시술 중에 전화 받느라 손 떨지 마세요",
        "sub": "디자이너별 예약 배정과 재방문 알림까지 알아서 챙겨드립니다.",
        "people": {"unit": "분", "counter": "분", "helped": "웃으며 돌아가셨어요",
                   "mission": "사람들이 거울 앞에서 웃게 만드세요"},
        "services": [
            {"name": "커트", "price": 25000, "duration": 60, "revisit_weeks": 4,
             "desc": "디자이너 1:1 맞춤 커트", "price_note": "25,000원 · 약 1시간"},
            {"name": "염색", "price": 80000, "duration": 120, "revisit_weeks": 6,
             "desc": "뿌리염색 · 전체염색", "price_note": "80,000원~ · 약 2시간"},
            {"name": "펌", "price": 90000, "duration": 150, "revisit_weeks": 12,
             "desc": "열펌 · 일반펌", "price_note": "90,000원~ · 약 2시간 30분"},
            {"name": "네일아트", "price": 55000, "duration": 90, "revisit_weeks": 3,
             "desc": "젤네일 기준", "price_note": "55,000원~ · 약 1시간 30분"},
        ],
        "designers": [
            {"name": "김지현", "specialty": "컷·펌 전문"},
            {"name": "박서준", "specialty": "염색·클리닉 전문"},
        ],
    },
    "moving": {
        "label": "이사·용달", "emoji": "🚚",
        "desc": "원룸이사 · 가정이사 · 용달",
        "headline": "견적 문의 전화에 하루가 다 가시죠?",
        "sub": "손님이 직접 조건을 입력하면 견적이 바로 계산되고 예약까지 이어집니다.",
        "people": {"unit": "가족", "counter": "가족", "helped": "새 출발을 하셨어요",
                   "mission": "새로운 시작을 함께하세요"},
        "services": [
            {"name": "원룸 이사", "price": 250000, "duration": 180,
             "desc": "1인 가구 · 용달 포함", "price_note": "기본 25만원~ (조건별 견적)"},
            {"name": "가정 이사", "price": 550000, "duration": 300,
             "desc": "투룸 이상 · 포장 포함", "price_note": "기본 55만원~ (조건별 견적)"},
            {"name": "용달", "price": 80000, "duration": 120,
             "desc": "짐만 옮기기", "price_note": "기본 8만원~ (거리별 견적)"},
        ],
        "checklist": [
            "귀중품·현금은 따로 챙기기",
            "냉장고 음식 비우기",
            "가전 플러그 뽑기",
            "관리사무소에 이사 통보",
            "주차 공간 확보",
            "잔금·계약서 확인",
            "새집 도어락 비밀번호 변경",
            "전입신고·우편물 이전 신청",
        ],
    },
}

KIND_LABEL = {"예약 확정": "예약 확정", "전날 리마인드": "전날 리마인드",
              "방문 감사": "방문 감사", "재방문 안내": "재방문 안내"}

# ---------------- 익명 벤치마크 (동네 평균 vs 사장님) ----------------
BENCH = {
    "cleaning": {"noshow": 18, "regular": 35, "unit": "청소업체"},
    "beauty": {"noshow": 22, "regular": 40, "unit": "미용실·네일샵"},
    "moving": {"noshow": 12, "regular": 25, "unit": "이사·용달"},
}

# ---------------- 바이럴: 동네 입소문 ----------------
ADOPTION = {  # 같은 동네 같은 업종 사용 가게 수 (시드)
    "cleaning": 14, "beauty": 22, "moving": 9,
}
AVG_REVENUE = {  # 동네 업종 평균 월 매출 (시드)
    "cleaning": 2800000, "beauty": 3500000, "moving": 4200000,
}
NEIGHBORS = {  # 이웃 자극용 익명 동네 가게 (시드)
    "cleaning": [
        {"name": "김○○청소", "bookings": 42},
        {"name": "박○○홈케어", "bookings": 35},
        {"name": "이○○클린", "bookings": 28},
    ],
    "beauty": [
        {"name": "김○○헤어", "bookings": 130},
        {"name": "박○○네일", "bookings": 98},
        {"name": "최○○미용실", "bookings": 87},
    ],
    "moving": [
        {"name": "김○○익스프레스", "bookings": 25},
        {"name": "박○○용달", "bookings": 19},
        {"name": "정○○이사", "bookings": 16},
    ],
}

# ---------------- 오프닝: 짜증 모먼트 ----------------
# 사장님의 실제 하루를 숫자로 재현 → "이제는 이렇게" 전환
PAIN = {
    "cleaning": {
        "stats": [
            {"emoji": "📞", "num": "2시간",
             "label": "하루 평균 전화·카톡 응대에 날리는 시간",
             "sub": "청소 한 건을 더 할 수 있는 시간입니다"},
            {"emoji": "💬", "num": "15건",
             "label": "'얼마예요?' 카톡 문의",
             "sub": "어제도 일일이 답하셨죠?"},
            {"emoji": "💸", "num": "45만원",
             "label": "월 노쇼 3건으로 날린 돈",
             "sub": "리마인드 문자 한 통이면 막을 수 있었습니다"},
        ],
        "timeline": [
            ("09:00", "현장 도착, 청소 시작"),
            ("09:15", "📞 전화 — \"입주청소 얼마예요?\" 20분 통화, 작업 중단"),
            ("13:00", "💬 카톡 15건 확인하느라 점심 거름"),
            ("18:00", "📞 내일 예약자 노쇼 — 빈 시간에 15만원 날림"),
        ],
        "fixes": [
            {"emoji": "📲", "title": "손님이 직접 예약",
             "desc": "전화 0통. 날짜·시간을 손님이 골라 신청하면 사장님은 확정 버튼만 누르세요."},
            {"emoji": "💬", "title": "확정·리마인드 문자 미리 준비",
             "desc": "노쇼 3건 → 0건에 도전. 전날 리마인드 문자가 알아서 갑니다."},
            {"emoji": "📷", "title": "청소 전후 사진 관리",
             "desc": "\"이 업체 실력 있네\" — 사진이 다음 예약을 부릅니다."},
        ],
    },
    "beauty": {
        "stats": [
            {"emoji": "📞", "num": "8통",
             "label": "시술 중에 울리는 하루 평균 전화",
             "sub": "손님 앞에서 전화 받으셨죠?"},
            {"emoji": "🪑", "num": "5건",
             "label": "월평균 노쇼 — 빈 의자가 곧 돈입니다",
             "sub": "리마인드 문자 한 통이면 막을 수 있었습니다"},
            {"emoji": "👋", "num": "6주",
             "label": "염색 주기를 놓치면 단골은 다른 집에 갑니다",
             "sub": "재방문 시기를 누가 챙겨줍니까?"},
        ],
        "timeline": [
            ("10:00", "첫 손님 커트 시작"),
            ("10:20", "📞 전화 — \"오늘 펌 돼요?\" 손 멈추고 10분 통화"),
            ("15:00", "🪑 예약 손님 노쇼 — 2시간 빈 의자"),
            ("19:00", "👋 지난달 염색 손님, 재방문 시기 지났는데 연락 못 함"),
        ],
        "fixes": [
            {"emoji": "📲", "title": "디자이너별 온라인 예약",
             "desc": "시술 중 전화 0통. 손님이 디자이너·시간을 직접 골라 예약합니다."},
            {"emoji": "💬", "title": "노쇼 방지 리마인드",
             "desc": "전날 자동 문자. 빈 의자를 없애는 가장 싼 방법입니다."},
            {"emoji": "🔁", "title": "재방문 주기 알림",
             "desc": "염색 6주, 커트 4주 — 시기가 되면 사장님 화면에 알려드립니다."},
        ],
    },
    "moving": {
        "stats": [
            {"emoji": "📞", "num": "10통",
             "label": "하루 평균 견적 문의 전화 (통화당 15분)",
             "sub": "2시간 반이 견적 상담으로 날아갑니다"},
            {"emoji": "📝", "num": "30분",
             "label": "견적서 1건 만드는 시간",
             "sub": "카톡 사진 받고, 계산하고, 보내고"},
            {"emoji": "📦", "num": "1건",
             "label": "이사 당일 빠뜨린 준비물",
             "sub": "사다리차 예약 깜빡, 현장에서 허둥댄 적 있으시죠?"},
        ],
        "timeline": [
            ("08:00", "📞 \"30평 이사 얼마예요?\" 첫 견적 전화"),
            ("11:00", "📝 카톡 사진 20장 받고 견적서 작성 30분"),
            ("14:00", "📞 \"아까 그 견적 다시 말해주세요\" 또 15분"),
            ("이사 당일", "📦 사다리차 예약 누락 — 현장에서 급히 수배"),
        ],
        "fixes": [
            {"emoji": "🧮", "title": "견적 자동 계산",
             "desc": "평수·거리·옵션을 손님이 입력하면 견적이 바로 계산됩니다."},
            {"emoji": "📲", "title": "견적 → 예약 한 번에",
             "desc": "견적 확인한 손님이 바로 날짜를 잡습니다. 전화 0통."},
            {"emoji": "✅", "title": "이사 당일 체크리스트",
             "desc": "준비물 8가지를 예약마다 자동 생성. 빠뜨림 걱정 끝."},
        ],
    },
}


def industry():
    ind = setting("industry")
    return ind if ind in INDUSTRIES else "cleaning"


def industry_info():
    return INDUSTRIES[industry()]


def tier_of(visits: int) -> str:
    if visits >= 5:
        return "VIP"
    if visits >= 2:
        return "단골"
    return "신규"


# ---------------- DB ----------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL UNIQUE,
        address TEXT DEFAULT '',
        memo TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price INTEGER NOT NULL DEFAULT 0,
        duration_min INTEGER NOT NULL DEFAULT 60,
        description TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        service_id INTEGER NOT NULL REFERENCES services(id),
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        price INTEGER NOT NULL DEFAULT 0,
        note TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        reservation_id INTEGER REFERENCES reservations(id),
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'scheduled',
        scheduled_at TEXT,
        sent_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS designers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialty TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reservation_id INTEGER NOT NULL REFERENCES reservations(id),
        kind TEXT NOT NULL,
        filename TEXT NOT NULL,
        uploaded_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS checklist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reservation_id INTEGER NOT NULL REFERENCES reservations(id),
        label TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        sort INTEGER NOT NULL DEFAULT 0
    );
    """)
    # 업종 특화 컬럼 (기존 DB 마이그레이션)
    for sql in [
        "ALTER TABLE services ADD COLUMN revisit_weeks INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE services ADD COLUMN price_note TEXT DEFAULT ''",
        "ALTER TABLE reservations ADD COLUMN designer_id INTEGER REFERENCES designers(id)",
        "ALTER TABLE reservations ADD COLUMN quote_json TEXT DEFAULT ''",
    ]:
        try:
            db.execute(sql)
        except sqlite3.OperationalError:
            pass
    defaults = {
        "industry": "",
        "shop_name": "맑음홈케어",
        "shop_desc": "우리 동네 믿고 맡기는 업체입니다.",
        "shop_phone": "010-1234-5678",
        "benefit_new": "첫 방문 감사 5% 할인 쿠폰",
        "benefit_regular": "단골 10% 할인 + 우선 예약",
        "benefit_vip": "VIP 15% 할인 + 명절 선물 + 최우선 예약",
        "tpl_confirm": "[{가게}] {이름}님, {날짜} {시간} {서비스} 예약이 확정되었습니다. 방문 전 연락드리겠습니다. - {가게}",
        "tpl_remind": "[{가게}] {이름}님, 내일 {시간} {서비스} 예약 잊지 않으셨죠? 변경은 {전화}로 연락주세요. - {가게}",
        "tpl_thanks": "[{가게}] {이름}님, 오늘 이용해주셔서 감사합니다! 다음 방문 때 {등급} 혜택을 챙겨드릴게요. - {가게}",
        "tpl_revisit": "[{가게}] {이름}님, {서비스} 받으신 지 {주}주가 다 되어가네요. 재방문 예약 도와드릴까요? - {가게}",
        "referral_code": "",
        "referral_visits": "0",
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    # 예전 DB(업종 도입 전)에 청소 데이터가 있으면 업종을 청소로 간주
    ind = db.execute("SELECT value FROM settings WHERE key='industry'").fetchone()["value"]
    if not ind:
        n = db.execute("SELECT COUNT(*) c FROM services").fetchone()["c"]
        if n > 0:
            db.execute("UPDATE settings SET value='cleaning' WHERE key='industry'")
    db.commit()
    db.close()
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def setting(key):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def render_tpl(template, customer, reservation=None, service=None, extra=None):
    visits = visit_count(customer["id"]) if customer else 0
    mapping = {
        "{가게}": setting("shop_name"),
        "{전화}": setting("shop_phone"),
        "{이름}": customer["name"] if customer else "",
        "{등급}": tier_of(visits),
        "{서비스}": service["name"] if service else "",
        "{날짜}": reservation["date"] if reservation else "",
        "{시간}": reservation["time"] if reservation else "",
        "{금액}": f"{reservation['price']:,}" if reservation else "",
    }
    if extra:
        mapping.update(extra)
    text = template
    for k, v in mapping.items():
        text = text.replace(k, str(v))
    return text


def visit_count(customer_id):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE customer_id=? AND status='completed'",
        (customer_id,)).fetchone()
    return row["c"]


def get_or_create_customer(name, phone, address=""):
    db = get_db()
    phone = "".join(c for c in phone if c.isdigit())
    row = db.execute("SELECT * FROM customers WHERE phone=?", (phone,)).fetchone()
    if row:
        return row["id"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = db.execute(
        "INSERT INTO customers(name, phone, address, created_at) VALUES (?, ?, ?, ?)",
        (name.strip(), phone, address.strip(), now))
    db.commit()
    return cur.lastrowid


def blocked_slots(rdate, rtime, duration_min, designer_id=None, exclude_id=None):
    """해당 예약이 차지하는 슬롯 목록"""
    start = int(rtime[:2])
    n = max(1, -(-duration_min // 60))
    return [f"{h:02d}:00" for h in range(start, min(start + n, 18))]


def slot_taken(rdate, rtime, duration_min=60, designer_id=None, exclude_id=None):
    """겹치는 예약이 있으면 True (소요시간·디자이너 고려)"""
    db = get_db()
    q = ("SELECT r.time, s.duration_min d, r.designer_id did FROM reservations r "
         "JOIN services s ON s.id=r.service_id "
         "WHERE r.date=? AND r.status IN ('pending','confirmed')")
    args = [rdate]
    if exclude_id:
        q += " AND r.id != ?"
        args.append(exclude_id)
    mine = set(blocked_slots(rdate, rtime, duration_min))
    for row in db.execute(q, args):
        if designer_id and row["did"] and row["did"] != designer_id:
            continue
        theirs = set(blocked_slots(rdate, row["time"], row["d"] or 60))
        if mine & theirs:
            return True
    return False


def free_designer(rdate, rtime, duration_min, exclude_id=None):
    db = get_db()
    for d in db.execute("SELECT * FROM designers WHERE active=1 ORDER BY id"):
        if not slot_taken(rdate, rtime, duration_min, designer_id=d["id"],
                          exclude_id=exclude_id):
            return d["id"]
    return None


def queue_message(customer_id, kind, content, reservation_id=None):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        """INSERT INTO messages(customer_id, reservation_id, kind, content,
                                status, scheduled_at, created_at)
           VALUES (?, ?, ?, ?, 'scheduled', ?, ?)""",
        (customer_id, reservation_id, kind, content, now, now))
    db.commit()


def customer_row(customer_id):
    db = get_db()
    return db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()


def reservation_detail(rid):
    db = get_db()
    return db.execute(
        """SELECT r.*, c.name AS cname, c.phone AS cphone, s.name AS sname,
                  s.duration_min AS sdur, d.name AS dname
           FROM reservations r
           JOIN customers c ON c.id = r.customer_id
           JOIN services s ON s.id = r.service_id
           LEFT JOIN designers d ON d.id = r.designer_id
           WHERE r.id=?""", (rid,)).fetchone()


def apply_industry(ind):
    """업종 변경: 서비스·디자이너·예약·문자 데이터를 업종 프리셋으로 교체"""
    db = get_db()
    db.execute("UPDATE settings SET value=? WHERE key='industry'", (ind,))
    db.execute("DELETE FROM checklist_items")
    db.execute("DELETE FROM photos")
    db.execute("DELETE FROM messages")
    db.execute("DELETE FROM reservations")
    db.execute("DELETE FROM designers")
    db.execute("DELETE FROM services")
    db.execute("DELETE FROM customers")
    db.commit()
    sys.path.insert(0, BASE_DIR)
    import seed
    seed.run(industry=ind, db_path=DB_PATH)
    # 가게 이름도 업종에 맞게 (사용자가 이미 바꿨으면 유지)
    names = {"cleaning": "맑음홈케어", "beauty": "단골헤어",
             "moving": "신속이사"}
    descs = {"cleaning": "우리 동네 믿고 맡기는 청소 전문 업체입니다.",
             "beauty": "우리 동네 단골 미용실입니다.",
             "moving": "우리 동네 믿고 맡기는 이사 전문 업체입니다."}
    db.execute("UPDATE settings SET value=? WHERE key='shop_name'", (names[ind],))
    db.execute("UPDATE settings SET value=? WHERE key='shop_desc'", (descs[ind],))
    db.commit()


# ---------------- 첫 화면: 업종 선택 ----------------
@app.route("/industry", methods=["GET", "POST"])
def industry_pick():
    if request.method == "POST":
        ind = request.form.get("industry", "")
        if ind in INDUSTRIES:
            apply_industry(ind)
            flash(f"{INDUSTRIES[ind]['emoji']} {INDUSTRIES[ind]['label']} 버전으로 준비됐습니다!")
            return redirect(url_for("home"))
    return render_template("industry_picker.html")


# ---------------- 첫 화면: 오프닝 (짜증 모먼트 → 해결책) ----------------
@app.route("/")
def index():
    db = get_db()
    ref = request.args.get("ref", "").strip()
    referred = False
    if ref:
        # 소개 링크로 방문: 카운트 증가 (시뮬레이션)
        try:
            n = int(setting("referral_visits") or "0") + 1
            db.execute("UPDATE settings SET value=? WHERE key='referral_visits'",
                       (str(n),))
            db.commit()
            referred = True
        except Exception:
            pass
    return render_template("opening.html", pain=PAIN, industries=INDUSTRIES,
                           hide_switch=True, referred=referred, ref=ref,
                           adoption=ADOPTION)


# ---------------- 손님용 화면 ----------------
@app.route("/home")
def home():
    if not setting("industry"):
        return redirect(url_for("index"))
    db = get_db()
    ind = industry()
    info = INDUSTRIES[ind]
    services = db.execute(
        "SELECT * FROM services WHERE active=1 ORDER BY price").fetchall()
    designers = db.execute(
        "SELECT * FROM designers WHERE active=1 ORDER BY id").fetchall() \
        if ind == "beauty" else []
    photos = []
    if ind == "cleaning":
        photos = db.execute(
            """SELECT p.*, r.date FROM photos p
               JOIN reservations r ON r.id=p.reservation_id
               ORDER BY p.id DESC LIMIT 6""").fetchall()
    return render_template("index.html", services=services, designers=designers,
                           photos=photos, info=info, ind=ind,
                           shop_name=setting("shop_name"),
                           shop_desc=setting("shop_desc"),
                           shop_phone=setting("shop_phone"),
                           today=date.today().isoformat())


@app.route("/slots")
def slots():
    """날짜별 예약 가능한 시간대 (소요시간·디자이너 고려)"""
    rdate = request.args.get("date", "")
    service_id = request.args.get("service_id", "")
    designer_id = request.args.get("designer_id", "")
    try:
        datetime.strptime(rdate, "%Y-%m-%d")
    except ValueError:
        return jsonify({"slots": []})
    db = get_db()
    svc = db.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    duration = (svc["duration_min"] or 60) if svc else 60
    n = max(1, -(-duration // 60))
    past = rdate < date.today().isoformat()
    did = int(designer_id) if designer_id and designer_id != "0" else None
    result = []
    for s in SLOTS:
        if past or int(s[:2]) + n > 18:
            result.append({"time": s, "open": False})
            continue
        if industry() == "beauty" and not did:
            # 디자이너 미지정: 한 명이라도 비어 있으면 가능
            ok = free_designer(rdate, s, duration) is not None
        else:
            ok = not slot_taken(rdate, s, duration, designer_id=did)
        result.append({"time": s, "open": ok})
    return jsonify({"slots": result, "duration": duration})


@app.route("/reserve", methods=["POST"])
def reserve():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    service_id = request.form.get("service_id", "")
    rdate = request.form.get("date", "")
    rtime = request.form.get("time", "")
    note = request.form.get("note", "").strip()
    designer_id = request.form.get("designer_id", "")
    quote_json = request.form.get("quote_json", "")

    digits = "".join(c for c in phone if c.isdigit())
    if not name or len(digits) < 10:
        flash("이름과 휴대폰 번호를 정확히 입력해주세요.")
        return redirect(url_for("home"))
    db = get_db()
    svc = db.execute("SELECT * FROM services WHERE id=? AND active=1",
                     (service_id,)).fetchone()
    if not svc:
        flash("서비스를 선택해주세요.")
        return redirect(url_for("home"))
    try:
        datetime.strptime(rdate, "%Y-%m-%d")
        if rdate < date.today().isoformat():
            raise ValueError
    except ValueError:
        flash("예약 날짜를 다시 선택해주세요.")
        return redirect(url_for("home"))

    duration = svc["duration_min"] or 60
    did = None
    if industry() == "beauty":
        if designer_id and designer_id != "0":
            did = int(designer_id)
        else:
            did = free_designer(rdate, rtime, duration)
            if not did:
                flash("선택하신 시간에 가능한 디자이너가 없습니다. 다른 시간을 골라주세요.")
                return redirect(url_for("home"))

    if rtime not in SLOTS or slot_taken(rdate, rtime, duration, designer_id=did):
        flash("선택하신 시간은 이미 예약이 찼습니다. 다른 시간을 골라주세요.")
        return redirect(url_for("home"))

    price = svc["price"]
    if industry() == "moving" and quote_json:
        try:
            q = json.loads(quote_json)
            price = int(q.get("total", price))
        except (ValueError, TypeError):
            pass

    cid = get_or_create_customer(name, digits)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = db.execute(
        """INSERT INTO reservations(customer_id, service_id, date, time, status,
                                    price, note, created_at, designer_id, quote_json)
           VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
        (cid, svc["id"], rdate, rtime, price, note, now, did, quote_json))
    rid = cur.lastrowid
    # 이사: 체크리스트 자동 생성
    if industry() == "moving":
        for i, label in enumerate(INDUSTRIES["moving"]["checklist"]):
            db.execute(
                "INSERT INTO checklist_items(reservation_id, label, sort) VALUES (?,?,?)",
                (rid, label, i))
    db.commit()
    return redirect(url_for("reserve_done", rid=rid))


@app.route("/reserve/done/<int:rid>")
def reserve_done(rid):
    r = reservation_detail(rid)
    if not r:
        return redirect(url_for("home"))
    quote = None
    if r["quote_json"]:
        try:
            quote = json.loads(r["quote_json"])
        except ValueError:
            pass
    return render_template("reserve_done.html", r=r, quote=quote,
                           shop_name=setting("shop_name"),
                           shop_phone=setting("shop_phone"),
                           status_label=STATUS_LABEL)


@app.route("/my", methods=["GET", "POST"])
def my_reservations():
    rows, phone = [], ""
    if request.method == "POST":
        phone = "".join(c for c in request.form.get("phone", "") if c.isdigit())
        if len(phone) >= 10:
            db = get_db()
            rows = db.execute(
                """SELECT r.*, s.name AS sname, d.name AS dname FROM reservations r
                   JOIN customers c ON c.id = r.customer_id
                   JOIN services s ON s.id = r.service_id
                   LEFT JOIN designers d ON d.id = r.designer_id
                   WHERE c.phone=? ORDER BY r.date DESC, r.time DESC""",
                (phone,)).fetchall()
        else:
            flash("휴대폰 번호를 정확히 입력해주세요.")
    return render_template("my.html", rows=rows, phone=phone,
                           shop_name=setting("shop_name"),
                           status_label=STATUS_LABEL)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------- 사장님용 화면 ----------------
@app.context_processor
def inject_nav():
    p = request.path
    admin = p.startswith("/admin")
    nav = ""
    if p == "/admin/briefing":
        nav = "brief"
    elif p == "/admin":
        nav = "dash"
    elif p.startswith("/admin/calendar"):
        nav = "cal"
    elif p.startswith("/admin/customers"):
        nav = "cust"
    elif p.startswith("/admin/tiers"):
        nav = "tier"
    elif p.startswith("/admin/messages"):
        nav = "msg"
    elif p.startswith("/admin/services"):
        nav = "svc"
    elif p.startswith("/admin/settings"):
        nav = "set"
    elif p.startswith("/admin/designers"):
        nav = "dgn"
    elif p.startswith("/admin/photos"):
        nav = "photo"
    ind = setting("industry") or "cleaning"
    pending_n = 0
    if admin:
        try:
            pending_n = get_db().execute(
                "SELECT COUNT(*) c FROM reservations WHERE status='pending'"
            ).fetchone()["c"]
        except Exception:
            pending_n = 0
    return {"admin": admin, "nav": nav, "ind": ind, "pending_n": pending_n,
            "ind_label": INDUSTRIES.get(ind, INDUSTRIES["cleaning"])["label"]}


@app.route("/admin")
def admin_dashboard():
    db = get_db()
    ind = industry()
    today = date.today().isoformat()
    monday = (date.today() - timedelta(days=date.today().weekday()))
    week_dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    today_rows = db.execute(
        """SELECT r.*, c.name cname, c.phone cphone, s.name sname, d.name dname
           FROM reservations r
           JOIN customers c ON c.id=r.customer_id
           JOIN services s ON s.id=r.service_id
           LEFT JOIN designers d ON d.id=r.designer_id
           WHERE r.date=? ORDER BY r.time""", (today,)).fetchall()

    rev = db.execute(
        """SELECT COALESCE(SUM(price),0) s FROM reservations
           WHERE date BETWEEN ? AND ? AND status IN ('pending','confirmed','completed')""",
        (week_dates[0], week_dates[-1])).fetchone()["s"]

    today_rev = db.execute(
        """SELECT COALESCE(SUM(price),0) s FROM reservations
           WHERE date=? AND status IN ('pending','confirmed','completed')""",
        (today,)).fetchone()["s"]

    month_start = date.today().replace(day=1).isoformat()
    regular_rev = db.execute(
        """SELECT COALESCE(SUM(r.price),0) s FROM reservations r
           WHERE r.date >= ? AND r.status='completed' AND r.customer_id IN (
             SELECT customer_id FROM reservations WHERE status='completed'
             GROUP BY customer_id HAVING COUNT(*) >= 2)""",
        (month_start,)).fetchone()["s"]

    bars = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        s = db.execute(
            """SELECT COALESCE(SUM(price),0) s FROM reservations
               WHERE date=? AND status IN ('pending','confirmed','completed')""",
            (d,)).fetchone()["s"]
        bars.append({"date": d[5:], "revenue": s, "is_today": d == today})

    total_customers = db.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]
    regulars = db.execute(
        """SELECT COUNT(*) c FROM (
             SELECT customer_id FROM reservations WHERE status='completed'
             GROUP BY customer_id HAVING COUNT(*) >= 2)""").fetchone()["c"]
    regular_ratio = round(regulars / total_customers * 100) if total_customers else 0

    noshow = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE status='noshow'").fetchone()["c"]
    done = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE status IN ('completed','noshow')"
    ).fetchone()["c"]
    noshow_rate = round(noshow / done * 100) if done else 0

    pending_n = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE status='pending'").fetchone()["c"]
    sched_n = db.execute(
        "SELECT COUNT(*) c FROM messages WHERE status='scheduled'").fetchone()["c"]
    recent_msgs = db.execute(
        """SELECT m.*, c.name cname FROM messages m
           JOIN customers c ON c.id=m.customer_id
           ORDER BY m.id DESC LIMIT 5""").fetchall()

    # 벤치마크 (동네 평균 vs 사장님)
    bench = BENCH[ind]

    # 이번 달 편하게 번 돈
    month_start_b = date.today().replace(day=1).isoformat()
    month_earned = db.execute(
        """SELECT COALESCE(SUM(price),0) s, COUNT(*) c FROM reservations
           WHERE date >= ? AND status='completed'""", (month_start_b,)).fetchone()

    # 미용실: 재방문 알림 (주기 지난 고객)
    revisit_alerts = []
    if ind == "beauty":
        for s in db.execute(
                "SELECT * FROM services WHERE active=1 AND revisit_weeks > 0"):
            weeks = s["revisit_weeks"]
            due = (date.today() - timedelta(weeks=weeks)).isoformat()
            soon = (date.today() - timedelta(weeks=weeks) + timedelta(days=7)).isoformat()
            for row in db.execute(
                    """SELECT c.id cid, c.name cname, c.phone cphone,
                              MAX(r.date) last_date
                       FROM reservations r JOIN customers c ON c.id=r.customer_id
                       WHERE r.service_id=? AND r.status='completed'
                       GROUP BY c.id HAVING last_date BETWEEN ? AND ?""",
                    (s["id"], due, soon)):
                future = db.execute(
                    """SELECT COUNT(*) c FROM reservations
                       WHERE customer_id=? AND date >= ? AND status IN ('pending','confirmed')""",
                    (row["cid"], today)).fetchone()["c"]
                if not future:
                    revisit_alerts.append({
                        "cid": row["cid"], "cname": row["cname"],
                        "phone": row["cphone"], "service": s["name"],
                        "service_id": s["id"],
                        "weeks": weeks, "last_date": row["last_date"]})

    # 이웃 자극: 오늘의 동네 가게 (날짜로 순환)
    neighbors = NEIGHBORS[ind]
    neighbor = neighbors[date.today().day % len(neighbors)]
    my_month_bookings = db.execute(
        """SELECT COUNT(*) c FROM reservations
           WHERE date >= ? AND status IN ('pending','confirmed','completed')""",
        (month_start_b,)).fetchone()["c"]

    # 존엄: 돈이 아니라 사람을 세기
    people = INDUSTRIES[ind]["people"]
    unit = people["unit"]
    if today_rows:
        dignity_today = f"오늘 {len(today_rows)}{unit}이 사장님 덕분에 {people['helped']}"
    else:
        dignity_today = ""
    dignity_month = (f"이번 달 사장님이 도운 {unit}: "
                     f"{month_earned['c']}{people['counter']}")

    return render_template(
        "admin_dashboard.html", today=today, today_rows=today_rows,
        week_revenue=rev, today_revenue=today_rev, regular_revenue=regular_rev,
        bars=bars, max_bar=max([b["revenue"] for b in bars] + [1]),
        regular_ratio=regular_ratio, regulars=regulars,
        total_customers=total_customers, noshow_rate=noshow_rate,
        noshow=noshow, pending_n=pending_n, sched_n=sched_n,
        recent_msgs=recent_msgs, revisit_alerts=revisit_alerts,
        bench=bench, month_earned=month_earned["s"],
        month_count=month_earned["c"],
        adoption=ADOPTION[ind], avg_revenue=AVG_REVENUE[ind],
        neighbor=neighbor, my_month_bookings=my_month_bookings,
        dignity_today=dignity_today, dignity_month=dignity_month,
        mission=people["mission"],
        status_label=STATUS_LABEL,
        shop_name=setting("shop_name"))


@app.route("/admin/briefing")
def admin_briefing():
    """사장님 오늘 브리핑 — 아침에 커피 마시며 보는 도파민 대시보드"""
    db = get_db()
    ind = industry()
    today = date.today().isoformat()
    hour = datetime.now().hour
    if 5 <= hour < 11:
        greeting = "좋은 아침이에요"
    elif 11 <= hour < 14:
        greeting = "점심은 드셨나요"
    elif 14 <= hour < 18:
        greeting = "오후도 힘내세요"
    else:
        greeting = "오늘 하루도 수고 많으셨어요"

    monday = date.today() - timedelta(days=date.today().weekday())
    week_dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    today_rows = db.execute(
        """SELECT r.*, c.name cname, s.name sname, d.name dname FROM reservations r
           JOIN customers c ON c.id=r.customer_id
           JOIN services s ON s.id=r.service_id
           LEFT JOIN designers d ON d.id=r.designer_id
           WHERE r.date=? ORDER BY r.time""", (today,)).fetchall()

    # 쓰나미 모먼트: 어제·오늘·내일 팀 수
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow_d = (date.today() + timedelta(days=1)).isoformat()
    today_n = len(today_rows)
    yesterday_n = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE date=? AND status IN ('pending','confirmed','completed')",
        (yesterday,)).fetchone()["c"]
    tomorrow_n = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE date=? AND status IN ('pending','confirmed')",
        (tomorrow_d,)).fetchone()["c"]
    today_done_n = len([r for r in today_rows if r["status"] == "completed"])

    if today_n > yesterday_n and yesterday_n > 0:
        compare_msg = f"어제({yesterday_n}팀)보다 많아요 😊"
    elif today_n == yesterday_n:
        compare_msg = "어제만큼 알차게 채워졌어요"
    elif yesterday_n == 0:
        compare_msg = "새로운 하루가 시작됐어요"
    else:
        compare_msg = "여유 있는 하루예요. 밀린 일을 정리해 보세요"

    week_rev = db.execute(
        """SELECT COALESCE(SUM(price),0) s FROM reservations
           WHERE date BETWEEN ? AND ? AND status IN ('pending','confirmed','completed')""",
        (week_dates[0], week_dates[-1])).fetchone()["s"]

    # 돌아온 단골: 이번 주 방문 예정인 단골/VIP
    returning = db.execute(
        """SELECT DISTINCT c.name FROM reservations r
           JOIN customers c ON c.id=r.customer_id
           WHERE r.date BETWEEN ? AND ? AND r.status IN ('pending','confirmed','completed')
           AND r.customer_id IN (
             SELECT customer_id FROM reservations WHERE status='completed'
             GROUP BY customer_id HAVING COUNT(*) >= 2)""",
        (week_dates[0], week_dates[-1])).fetchall()

    # 이번 달 편하게 번 돈 (완료 매출)
    month_start = date.today().replace(day=1).isoformat()
    month_earned = db.execute(
        """SELECT COALESCE(SUM(price),0) s, COUNT(*) c FROM reservations
           WHERE date >= ? AND status='completed'""", (month_start,)).fetchone()

    pending_n = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE status='pending'").fetchone()["c"]
    sched_n = db.execute(
        "SELECT COUNT(*) c FROM messages WHERE status='scheduled'").fetchone()["c"]

    todos = []
    if pending_n:
        todos.append({"emoji": "⏳", "text": f"확정이 필요한 예약 {pending_n}건",
                      "url": url_for("admin_calendar")})
    if sched_n:
        todos.append({"emoji": "📨", "text": f"보낼 문자 {sched_n}건 준비됨",
                      "url": url_for("admin_messages")})
    if ind == "beauty":
        todos.append({"emoji": "🔁", "text": "재방문 시기인 고객 확인하기",
                      "url": url_for("admin_dashboard")})
    if ind == "moving":
        todos.append({"emoji": "✅", "text": "이사 체크리스트 확인하기",
                      "url": url_for("admin_calendar")})
    if not todos:
        todos.append({"emoji": "☕", "text": "급한 일 없어요. 커피 한 잔 하세요",
                      "url": url_for("admin_dashboard")})

    cheers = [
        "사장님은 일만 하세요. 나머지는 제가 챙길게요.",
        "단골이 다시 찾는 가게, 그게 사장님 가게입니다.",
        "오늘도 마음 편한 하루 되세요.",
    ]
    cheer = cheers[date.today().day % len(cheers)]

    # 쓰나미 트리거: 누군가 챙겨주고 있음 (존엄: 사람을 세기)
    shop = setting("shop_name")
    people = INDUSTRIES[ind]["people"]
    unit = people["unit"]
    tsunami = (f"오늘 하루 수고하셨어요. {today_n}{unit}이 사장님을 찾아왔고, "
               f"내일은 {tomorrow_n}{unit}이 예약되어 있어요.")
    is_evening = hour >= 18
    if today_n:
        dignity_today = f"오늘 {today_n}{unit}이 사장님 덕분에 {people['helped']}"
    else:
        dignity_today = "오늘은 쉬는 날이에요. 푹 쉬세요"
    month_helped_n = month_earned["c"]
    dignity_month = f"이번 달 사장님이 도운 {unit}: {month_helped_n}{people['counter']}"

    return render_template(
        "admin_briefing.html", greeting=greeting, today=today,
        today_rows=today_rows, today_n=today_n, yesterday_n=yesterday_n,
        tomorrow_n=tomorrow_n, today_done_n=today_done_n,
        compare_msg=compare_msg, tsunami=tsunami, shop=shop,
        is_evening=is_evening, dignity_today=dignity_today,
        dignity_month=dignity_month, mission=people["mission"], unit=unit,
        week_revenue=week_rev,
        returning=returning, month_earned=month_earned["s"],
        month_count=month_earned["c"], todos=todos, cheer=cheer,
        status_label=STATUS_LABEL, shop_name=shop)


@app.route("/admin/calendar")
def admin_calendar():
    week_offset = request.args.get("w", "0")
    try:
        week_offset = int(week_offset)
    except ValueError:
        week_offset = 0
    week_offset = max(-52, min(52, week_offset))
    monday = date.today() - timedelta(days=date.today().weekday()) \
        + timedelta(weeks=week_offset)
    days = [monday + timedelta(days=i) for i in range(7)]
    db = get_db()
    services = db.execute(
        "SELECT * FROM services WHERE active=1 ORDER BY price").fetchall()
    designers = db.execute(
        "SELECT * FROM designers WHERE active=1 ORDER BY id").fetchall()
    grid = {d.isoformat(): {} for d in days}
    for r in db.execute(
            """SELECT r.*, c.name cname, s.name sname, d.name dname
               FROM reservations r
               JOIN customers c ON c.id=r.customer_id
               JOIN services s ON s.id=r.service_id
               LEFT JOIN designers d ON d.id=r.designer_id
               WHERE r.date BETWEEN ? AND ?""",
            (days[0].isoformat(), days[-1].isoformat())):
        grid[r["date"]].setdefault(r["time"], []).append(r)
    return render_template("admin_calendar.html", days=days, slots=SLOTS,
                           grid=grid, week_offset=week_offset,
                           today=date.today().isoformat(),
                           status_label=STATUS_LABEL,
                           services=services, designers=designers,
                           shop_name=setting("shop_name"))


@app.route("/admin/calendar/add", methods=["POST"])
def admin_calendar_add():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    service_id = request.form.get("service_id", "")
    rdate = request.form.get("date", "")
    rtime = request.form.get("time", "")
    note = request.form.get("note", "").strip()
    designer_id = request.form.get("designer_id", "")
    digits = "".join(c for c in phone if c.isdigit())

    db = get_db()
    svc = db.execute("SELECT * FROM services WHERE id=? AND active=1",
                     (service_id,)).fetchone()
    did = int(designer_id) if designer_id else None
    duration = (svc["duration_min"] or 60) if svc else 60
    err = None
    if not name or len(digits) < 10:
        err = "고객 이름과 휴대폰 번호를 입력해주세요."
    elif not svc:
        err = "서비스를 선택해주세요."
    elif rtime not in SLOTS:
        err = "시간을 선택해주세요."
    elif slot_taken(rdate, rtime, duration, designer_id=did):
        err = f"{rdate} {rtime}에는 이미 예약이 있습니다."
    if err:
        flash(err)
        return redirect(url_for("admin_calendar"))

    cid = get_or_create_customer(name, digits)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = db.execute(
        """INSERT INTO reservations(customer_id, service_id, date, time,
                                    status, price, note, created_at, designer_id)
           VALUES (?, ?, ?, ?, 'confirmed', ?, ?, ?, ?)""",
        (cid, svc["id"], rdate, rtime, svc["price"], note, now, did))
    if industry() == "moving":
        for i, label in enumerate(INDUSTRIES["moving"]["checklist"]):
            db.execute(
                "INSERT INTO checklist_items(reservation_id, label, sort) VALUES (?,?,?)",
                (cur.lastrowid, label, i))
    db.commit()
    flash(f"{name}님 {rdate} {rtime} 예약이 등록되었습니다.")
    return redirect(url_for("admin_calendar"))


@app.route("/admin/reservations/<int:rid>")
def reservation_page(rid):
    r = reservation_detail(rid)
    if not r:
        flash("예약을 찾을 수 없습니다.")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    checklist = db.execute(
        "SELECT * FROM checklist_items WHERE reservation_id=? ORDER BY sort",
        (rid,)).fetchall()
    photos = db.execute(
        "SELECT * FROM photos WHERE reservation_id=? ORDER BY kind", (rid,)).fetchall()
    quote = None
    if r["quote_json"]:
        try:
            quote = json.loads(r["quote_json"])
        except ValueError:
            pass
    return render_template("admin_reservation_detail.html", r=r,
                           checklist=checklist, photos=photos, quote=quote,
                           status_label=STATUS_LABEL,
                           shop_name=setting("shop_name"))


@app.route("/admin/reservations/<int:rid>/status", methods=["POST"])
def reservation_status(rid):
    action = request.form.get("action", "")
    r = reservation_detail(rid)
    if not r:
        flash("예약을 찾을 수 없습니다.")
        return redirect(url_for("admin_dashboard"))

    db = get_db()
    customer = customer_row(r["customer_id"])
    service = db.execute("SELECT * FROM services WHERE id=?",
                         (r["service_id"],)).fetchone()

    if action == "confirm" and r["status"] == "pending":
        duration = (service["duration_min"] or 60) if service else 60
        if slot_taken(r["date"], r["time"], duration,
                      designer_id=r["designer_id"], exclude_id=rid):
            flash("같은 시간에 다른 예약이 있어 확정할 수 없습니다.")
        else:
            db.execute("UPDATE reservations SET status='confirmed' WHERE id=?", (rid,))
            content = render_tpl(setting("tpl_confirm"), customer, r, service)
            queue_message(customer["id"], "예약 확정", content, rid)
            flash(f"{customer['name']}님 예약이 확정되었습니다. 확정 문자도 예약되었습니다.")
    elif action == "complete" and r["status"] in ("pending", "confirmed"):
        db.execute("UPDATE reservations SET status='completed' WHERE id=?", (rid,))
        db.commit()
        visits = visit_count(customer["id"])
        tier = tier_of(visits)
        content = render_tpl(setting("tpl_thanks"), customer, r, service)
        queue_message(customer["id"], "방문 감사", content, rid)
        flash(f"방문 완료 처리되었습니다. {customer['name']}님은 현재 '{tier}' 등급입니다 "
              f"(총 {visits}회 방문). 감사 문자도 예약되었습니다.")
    elif action == "cancel" and r["status"] in ("pending", "confirmed"):
        db.execute("UPDATE reservations SET status='cancelled' WHERE id=?", (rid,))
        flash("예약이 취소되었습니다.")
    elif action == "noshow" and r["status"] in ("pending", "confirmed"):
        db.execute("UPDATE reservations SET status='noshow' WHERE id=?", (rid,))
        flash("노쇼로 기록되었습니다. 다음 예약 시 참고하세요.")
    else:
        flash("처리할 수 없는 상태입니다.")
    db.commit()
    return redirect(request.form.get("next", url_for("admin_dashboard")))


@app.route("/admin/checklist/<int:item_id>/toggle", methods=["POST"])
def checklist_toggle(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM checklist_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        flash("항목을 찾을 수 없습니다.")
        return redirect(url_for("admin_dashboard"))
    db.execute("UPDATE checklist_items SET done = 1 - done WHERE id=?", (item_id,))
    db.commit()
    return redirect(url_for("reservation_page", rid=item["reservation_id"]))


@app.route("/admin/checklist/add", methods=["POST"])
def checklist_add():
    rid = request.form.get("reservation_id", "")
    label = request.form.get("label", "").strip()
    db = get_db()
    r = db.execute("SELECT id FROM reservations WHERE id=?", (rid,)).fetchone()
    if not r:
        flash("예약을 찾을 수 없습니다.")
        return redirect(url_for("admin_dashboard"))
    if not label:
        flash("항목 내용을 입력해주세요.")
    else:
        mx = db.execute(
            "SELECT COALESCE(MAX(sort),-1) m FROM checklist_items WHERE reservation_id=?",
            (rid,)).fetchone()["m"]
        db.execute(
            "INSERT INTO checklist_items(reservation_id, label, sort) VALUES (?,?,?)",
            (rid, label, mx + 1))
        db.commit()
        flash("체크리스트에 추가되었습니다.")
    return redirect(url_for("reservation_page", rid=rid))


# ----- 고객 명단 -----
@app.route("/admin/customers")
def admin_customers():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        rows = db.execute(
            "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
            (f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    enriched = []
    for c in rows:
        v = visit_count(c["id"])
        enriched.append({"row": c, "visits": v, "tier": tier_of(v)})
    total_visits = db.execute(
        "SELECT COUNT(*) c FROM reservations WHERE status='completed'").fetchone()["c"]
    return render_template("admin_customers.html", customers=enriched, q=q,
                           total_visits=total_visits,
                           shop_name=setting("shop_name"))


@app.route("/admin/customers/<int:cid>", methods=["GET", "POST"])
def admin_customer_detail(cid):
    db = get_db()
    c = customer_row(cid)
    if not c:
        flash("고객을 찾을 수 없습니다.")
        return redirect(url_for("admin_customers"))
    if request.method == "POST":
        memo = request.form.get("memo", "")
        db.execute("UPDATE customers SET memo=? WHERE id=?", (memo, cid))
        db.commit()
        flash("메모가 저장되었습니다.")
        return redirect(url_for("admin_customer_detail", cid=cid))
    visits = db.execute(
        """SELECT r.*, s.name sname, d.name dname FROM reservations r
           JOIN services s ON s.id=r.service_id
           LEFT JOIN designers d ON d.id=r.designer_id
           WHERE r.customer_id=? ORDER BY r.date DESC, r.time DESC""",
        (cid,)).fetchall()
    msgs = db.execute(
        "SELECT * FROM messages WHERE customer_id=? ORDER BY id DESC LIMIT 10",
        (cid,)).fetchall()
    v = len([x for x in visits if x["status"] == "completed"])
    return render_template("admin_customer_detail.html", c=c, visits=visits,
                           msgs=msgs, visit_count=v, tier=tier_of(v),
                           benefit={
                               "신규": setting("benefit_new"),
                               "단골": setting("benefit_regular"),
                               "VIP": setting("benefit_vip")},
                           status_label=STATUS_LABEL,
                           shop_name=setting("shop_name"))


@app.route("/admin/customers/add", methods=["POST"])
def admin_customer_add():
    name = request.form.get("name", "").strip()
    phone = "".join(c for c in request.form.get("phone", "") if c.isdigit())
    address = request.form.get("address", "").strip()
    if not name or len(phone) < 10:
        flash("이름과 휴대폰 번호를 정확히 입력해주세요.")
        return redirect(url_for("admin_customers"))
    db = get_db()
    exists = db.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
    if exists:
        flash("이미 등록된 번호입니다. 고객 명단에서 찾아보세요.")
        return redirect(url_for("admin_customers"))
    get_or_create_customer(name, phone, address)
    flash(f"{name}님이 고객 명단에 등록되었습니다.")
    return redirect(url_for("admin_customers"))


# ----- 단골 등급 -----
@app.route("/admin/tiers", methods=["GET", "POST"])
def admin_tiers():
    db = get_db()
    if request.method == "POST":
        for key in ("benefit_new", "benefit_regular", "benefit_vip"):
            db.execute("UPDATE settings SET value=? WHERE key=?",
                       (request.form.get(key, ""), key))
        db.commit()
        flash("등급별 혜택 내용이 저장되었습니다.")
        return redirect(url_for("admin_tiers"))
    counts = {"신규": 0, "단골": 0, "VIP": 0}
    for c in db.execute("SELECT id FROM customers"):
        counts[tier_of(visit_count(c["id"]))] += 1
    return render_template("admin_tiers.html", counts=counts,
                           benefit_new=setting("benefit_new"),
                           benefit_regular=setting("benefit_regular"),
                           benefit_vip=setting("benefit_vip"),
                           shop_name=setting("shop_name"))


# ----- 자동 문자 -----
@app.route("/admin/messages", methods=["GET", "POST"])
def admin_messages():
    db = get_db()
    if request.method == "POST":
        for key in ("tpl_confirm", "tpl_remind", "tpl_thanks", "tpl_revisit"):
            db.execute("UPDATE settings SET value=? WHERE key=?",
                       (request.form.get(key, ""), key))
        db.commit()
        flash("문자 내용이 저장되었습니다.")
        return redirect(url_for("admin_messages"))
    scheduled = db.execute(
        """SELECT m.*, c.name cname, c.phone cphone FROM messages m
           JOIN customers c ON c.id=m.customer_id
           WHERE m.status='scheduled' ORDER BY m.id DESC""").fetchall()
    sent = db.execute(
        """SELECT m.*, c.name cname, c.phone cphone FROM messages m
           JOIN customers c ON c.id=m.customer_id
           WHERE m.status='sent' ORDER BY m.id DESC LIMIT 30""").fetchall()
    return render_template(
        "admin_messages.html", scheduled=scheduled, sent=sent,
        tpl_confirm=setting("tpl_confirm"), tpl_remind=setting("tpl_remind"),
        tpl_thanks=setting("tpl_thanks"), tpl_revisit=setting("tpl_revisit"),
        shop_name=setting("shop_name"),
        kind_label=KIND_LABEL)


@app.route("/admin/messages/send", methods=["POST"])
def admin_messages_send():
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = db.execute(
        "UPDATE messages SET status='sent', sent_at=? WHERE status='scheduled'",
        (now,)).rowcount
    db.commit()
    flash(f"{n}건의 문자를 발송했습니다. (데모라서 실제로는 전송되지 않습니다)")
    return redirect(url_for("admin_messages"))


@app.route("/admin/messages/remind", methods=["POST"])
def admin_messages_remind():
    db = get_db()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    rows = db.execute(
        """SELECT r.*, c.id cid FROM reservations r
           JOIN customers c ON c.id=r.customer_id
           WHERE r.date=? AND r.status='confirmed'""", (tomorrow,)).fetchall()
    n = 0
    for r in rows:
        dup = db.execute(
            "SELECT COUNT(*) c FROM messages WHERE reservation_id=? AND kind='전날 리마인드'",
            (r["id"],)).fetchone()["c"]
        if dup:
            continue
        customer = customer_row(r["cid"])
        service = db.execute("SELECT * FROM services WHERE id=?",
                             (r["service_id"],)).fetchone()
        content = render_tpl(setting("tpl_remind"), customer, r, service)
        queue_message(customer["id"], "전날 리마인드", content, r["id"])
        n += 1
    flash(f"내일({tomorrow}) 확정 예약 {n}건에 리마인드 문자를 예약했습니다.")
    return redirect(url_for("admin_messages"))


@app.route("/admin/revisit/<int:cid>/send", methods=["POST"])
def revisit_send(cid):
    """미용실: 재방문 안내 문자 예약"""
    db = get_db()
    c = customer_row(cid)
    if not c:
        flash("고객을 찾을 수 없습니다.")
        return redirect(url_for("admin_dashboard"))
    service_id = request.form.get("service_id", "")
    service = db.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    if not service:
        flash("서비스를 찾을 수 없습니다.")
        return redirect(url_for("admin_dashboard"))
    content = render_tpl(setting("tpl_revisit"), c, None, service,
                         extra={"{주}": service["revisit_weeks"] or ""})
    queue_message(c["id"], "재방문 안내", content)
    flash(f"{c['name']}님께 재방문 안내 문자를 예약했습니다.")
    return redirect(url_for("admin_dashboard"))


# ----- 디자이너 (미용실) -----
@app.route("/admin/designers", methods=["GET", "POST"])
def admin_designers():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        specialty = request.form.get("specialty", "").strip()
        if not name:
            flash("디자이너 이름을 입력해주세요.")
        else:
            db.execute("INSERT INTO designers(name, specialty) VALUES (?, ?)",
                       (name, specialty))
            db.commit()
            flash(f"{name} 디자이너가 등록되었습니다.")
        return redirect(url_for("admin_designers"))
    designers = db.execute("SELECT * FROM designers ORDER BY active DESC, id").fetchall()
    counts = {}
    for d in designers:
        counts[d["id"]] = db.execute(
            """SELECT COUNT(*) c FROM reservations
               WHERE designer_id=? AND status IN ('pending','confirmed')""",
            (d["id"],)).fetchone()["c"]
    return render_template("admin_designers.html", designers=designers,
                           counts=counts, shop_name=setting("shop_name"))


@app.route("/admin/designers/<int:did>/toggle", methods=["POST"])
def admin_designer_toggle(did):
    db = get_db()
    db.execute("UPDATE designers SET active = 1 - active WHERE id=?", (did,))
    db.commit()
    return redirect(url_for("admin_designers"))


# ----- 작업 사진 (청소) -----
@app.route("/admin/photos", methods=["GET", "POST"])
def admin_photos():
    db = get_db()
    if request.method == "POST":
        rid = request.form.get("reservation_id", "")
        kind = request.form.get("kind", "")
        f = request.files.get("photo")
        r = db.execute("SELECT id FROM reservations WHERE id=?", (rid,)).fetchone()
        if not r:
            flash("예약을 찾을 수 없습니다.")
        elif kind not in ("before", "after"):
            flash("전/후 구분을 선택해주세요.")
        elif not f or not f.filename:
            flash("사진 파일을 선택해주세요.")
        else:
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext not in ALLOWED_EXT:
                flash("사진 파일(jpg, png 등)만 올릴 수 있습니다.")
            else:
                fname = f"r{rid}_{kind}_{int(time.time())}.{ext}"
                f.save(os.path.join(UPLOAD_DIR, secure_filename(fname)))
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 같은 예약·구분은 최신 1장으로 교체
                old = db.execute(
                    "SELECT * FROM photos WHERE reservation_id=? AND kind=?",
                    (rid, kind)).fetchone()
                if old:
                    try:
                        os.remove(os.path.join(UPLOAD_DIR, old["filename"]))
                    except OSError:
                        pass
                    db.execute("DELETE FROM photos WHERE id=?", (old["id"],))
                db.execute(
                    "INSERT INTO photos(reservation_id, kind, filename, uploaded_at)"
                    " VALUES (?,?,?,?)", (rid, kind, fname, now))
                db.commit()
                flash("작업 사진이 등록되었습니다.")
        return redirect(url_for("admin_photos"))
    done = db.execute(
        """SELECT r.*, c.name cname, s.name sname FROM reservations r
           JOIN customers c ON c.id=r.customer_id
           JOIN services s ON s.id=r.service_id
           WHERE r.status='completed' ORDER BY r.date DESC LIMIT 20""").fetchall()
    gallery = db.execute(
        """SELECT p.*, r.date, c.name cname, s.name sname FROM photos p
           JOIN reservations r ON r.id=p.reservation_id
           JOIN customers c ON c.id=r.customer_id
           JOIN services s ON s.id=r.service_id
           ORDER BY p.id DESC LIMIT 24""").fetchall()
    return render_template("admin_photos.html", done=done, gallery=gallery,
                           shop_name=setting("shop_name"))


# ----- 서비스 / 가게 설정 -----
@app.route("/admin/services", methods=["GET", "POST"])
def admin_services():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            price = int(request.form.get("price", "0").replace(",", ""))
        except ValueError:
            price = 0
        if not name:
            flash("서비스 이름을 입력해주세요.")
        else:
            db.execute(
                "INSERT INTO services(name, price, description) VALUES (?, ?, ?)",
                (name, max(0, price),
                 request.form.get("description", "").strip()))
            db.commit()
            flash(f"'{name}' 서비스가 추가되었습니다.")
        return redirect(url_for("admin_services"))
    services = db.execute("SELECT * FROM services ORDER BY active DESC, price").fetchall()
    return render_template("admin_services.html", services=services,
                           shop_name=setting("shop_name"))


@app.route("/admin/services/<int:sid>/toggle", methods=["POST"])
def admin_service_toggle(sid):
    db = get_db()
    db.execute("UPDATE services SET active = 1 - active WHERE id=?", (sid,))
    db.commit()
    return redirect(url_for("admin_services"))


@app.route("/admin/referral/create", methods=["POST"])
def referral_create():
    """소개 링크 생성 시뮬레이션"""
    import random
    import string
    db = get_db()
    code = setting("referral_code")
    if not code:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        db.execute("UPDATE settings SET value=? WHERE key='referral_code'", (code,))
        db.commit()
    flash("소개 링크가 만들어졌어요. 옆 가게 사장님께 건네보세요 🎁")
    return redirect(url_for("admin_settings"))


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    db = get_db()
    if request.method == "POST":
        if "industry" in request.form and request.form["industry"] in INDUSTRIES:
            new_ind = request.form["industry"]
            if new_ind != industry():
                apply_industry(new_ind)
                flash(f"{INDUSTRIES[new_ind]['label']} 버전으로 바뀌었습니다. "
                      "서비스·예약 데이터가 새 업종에 맞게 준비됩니다.")
                return redirect(url_for("admin_settings"))
        for key in ("shop_name", "shop_desc", "shop_phone"):
            db.execute("UPDATE settings SET value=? WHERE key=?",
                       (request.form.get(key, ""), key))
        db.commit()
        flash("가게 정보가 저장되었습니다.")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html",
                           shop_name=setting("shop_name"),
                           shop_desc=setting("shop_desc"),
                           shop_phone=setting("shop_phone"),
                           industries=INDUSTRIES,
                           current_industry=industry(),
                           referral_code=setting("referral_code"),
                           referral_visits=setting("referral_visits") or "0")


@app.route("/admin/share-image")
def share_image():
    """월간 리포트 공유 이미지 자동 생성 (단톡방 자랑용)"""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    db = get_db()
    ind = industry()
    month_start = date.today().replace(day=1).isoformat()
    row = db.execute(
        """SELECT COALESCE(SUM(price),0) s, COUNT(*) c FROM reservations
           WHERE date >= ? AND status='completed'""", (month_start,)).fetchone()
    earned, count = row["s"], row["c"]
    avg = AVG_REVENUE[ind]
    pct = round((earned - avg) / avg * 100) if avg else 0
    manwon = earned // 10000

    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), "#f6f4ef")
    d = ImageDraw.Draw(img)
    fb = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    fr = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    f_title = ImageFont.truetype(fb, 72)
    f_big = ImageFont.truetype(fb, 150)
    f_mid = ImageFont.truetype(fb, 56)
    f_small = ImageFont.truetype(fr, 40)
    ink, brand, green, muted = "#2b2620", "#b25f17", "#2e8b57", "#8a8272"

    # 상단 바
    d.rectangle([0, 0, W, 26], fill="#d97b2b")
    d.text((80, 90), "이번 달 성적표", font=f_title, fill=ink)
    d.text((80, 190), f"{setting('shop_name')} 사장님", font=f_mid, fill=muted)

    # 핵심 숫자
    y = 420
    d.text((80, y), "이번 달", font=f_mid, fill=ink)
    d.text((80, y + 90), f"{manwon:,}만원", font=f_big, fill=green)
    d.text((80, y + 290), "더 벌었어요!", font=f_big, fill=green)
    if pct >= 0:
        d.text((80, y + 480), f"동네 평균보다 {pct}% 더!", font=f_mid, fill=brand)
    else:
        d.text((80, y + 480), "다음 달은 더 크게!", font=f_mid, fill=brand)
    d.text((80, y + 580), f"완료 {count}건 · 전화 응대 없이", font=f_small, fill=muted)
    people = INDUSTRIES[ind]["people"]
    d.text((80, y + 640), f"도운 {people['unit']}: {count}{people['counter']} · 사장님 덕분입니다",
           font=f_small, fill=green)

    # 하단
    d.rectangle([0, H - 220, W, H], fill="#2b2620")
    d.text((80, H - 160), "사장님 최고예요.", font=f_mid, fill="#f6f4ef")
    d.text((80, H - 90), "놓치고 있던 돈을 찾아주는 시스템", font=f_small, fill="#8a8272")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype="image/png",
                     download_name="이번달_성적표.png", as_attachment=True)


@app.route("/admin/customers/export")
def customers_export():
    """고객 데이터 내려받기 — 데이터는 10년 후에도 사장님의 것"""
    import csv
    from io import StringIO
    from flask import Response
    db = get_db()
    out = StringIO()
    w = csv.writer(out)
    w.writerow(["이름", "전화번호", "주소", "방문횟수", "등급", "메모"])
    for c in db.execute("SELECT * FROM customers ORDER BY name"):
        v = visit_count(c["id"])
        w.writerow([c["name"], c["phone"], c["address"], v, tier_of(v), c["memo"]])
    data = "\ufeff" + out.getvalue()  # 엑셀 한글 깨짐 방지
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             "attachment; filename*=UTF-8''%EA%B3%A0%EA%B0%9D%EB%AA%85%EB%8B%A8.csv"})


@app.route("/about")
def about():
    return render_template("about.html", hide_switch=True,
                           shop_name=setting("shop_name"))


# ---------------- 에러 처리 ----------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", shop_name=setting("shop_name")), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html", shop_name=setting("shop_name")), 500


@app.errorhandler(413)
def too_large(e):
    flash("파일이 너무 큽니다. 8MB 이하의 사진만 올릴 수 있습니다.")
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.errorhandler(Exception)
def unhandled(e):
    app.logger.exception("unhandled error")
    try:
        return render_template("500.html", shop_name=setting("shop_name")), 500
    except Exception:
        return "일시적인 문제가 생겼습니다. 잠시 후 다시 시도해주세요.", 500


if __name__ == "__main__":
    port = 5004
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (ValueError, IndexError):
            pass
    init_db()
    app.run(host="0.0.0.0", port=port, debug=False)
