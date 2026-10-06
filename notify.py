#!/usr/bin/env python3
"""
JabraTL -> Discord notifier
Reads the public Blogger feeds and posts to Discord webhooks when
  * a new chapter is published   -> CHAPTER_WEBHOOK  (+ role ping)
  * a new novel page is created  -> NOVEL_WEBHOOK    (optional)
Secrets come from environment variables (GitHub Actions Secrets).
"""
import json, os, re, sys, time, html, urllib.request, urllib.error

# ----------------------------- SETTINGS (edit me) -----------------------------
SITE_URL         = os.environ.get("SITE_URL", "https://jabratl.blogspot.com").rstrip("/")
SITE_NAME        = "JabraTL"
BOT_NAME         = "JabraTL Updates"        # name shown on every message
BOT_AVATAR       = ""                       # optional: direct image URL for the bot avatar
EMBED_COLOR      = 0x087C85                 # teal. Change if you like
NOVEL_LABEL_PREFIX = "Novel-"               # chapters carry a label starting with this
FEED_SIZE        = 40                       # how many latest items to check each run
MILESTONE_EVERY  = 50                       # celebrate chapter 50, 100, 150 ... (0 = off)
MAX_LIST         = 12                       # max chapter links shown in a bulk-release message
# Optional: one role per novel so readers can follow only the novels they like.
#   "Novel-Label-Exactly-As-In-Blogger": "DISCORD_ROLE_ID"
ROLE_MAP = {
    # "Novel-My-First-Novel": "123456789012345678",
}
# ------------------------------------------------------------------------------

CHAPTER_WEBHOOK = os.environ.get("CHAPTER_WEBHOOK", "").strip()
NOVEL_WEBHOOK   = os.environ.get("NOVEL_WEBHOOK", "").strip()
CHAPTER_ROLE    = os.environ.get("CHAPTER_ROLE_ID", "").strip()
NOVEL_ROLE      = os.environ.get("NOVEL_ROLE_ID", "").strip()
DRY_RUN         = os.environ.get("DRY_RUN", "0") == "1"
TEST_LATEST     = os.environ.get("TEST_LATEST", "0") == "1"
STATE_FILE      = "state.json"
UA              = "DiscordBot (https://github.com, 1.0) JabraTL-notifier"


def log(*a):
    print(*a, flush=True)


def http(url, data=None, tries=4):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode("utf-8")
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
                return r.status, body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429:                      # Discord rate limit
                try:
                    wait = float(json.loads(body).get("retry_after", 2))
                except Exception:
                    wait = 2
                log("rate limited, waiting", wait)
                time.sleep(min(wait + 0.5, 30))
                last = (e.code, body)
                continue
            if 500 <= e.code < 600:
                time.sleep(2 * (i + 1)); last = (e.code, body); continue
            return e.code, body
        except Exception as e:                      # network hiccup
            time.sleep(2 * (i + 1)); last = (0, str(e))
    return last or (0, "failed")


def get_feed(kind):
    url = f"{SITE_URL}/feeds/{kind}/default?alt=json&max-results={FEED_SIZE}"
    code, body = http(url)
    if code != 200:
        raise RuntimeError(f"Could not read {kind} feed ({code}): {body[:200]}")
    return (json.loads(body).get("feed", {}).get("entry")) or []


# ------------------------------- helpers --------------------------------------
def to_text(h):
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", h or "")
    h = re.sub(r"<[^>]+>", "", h)
    return html.unescape(h).replace("\xa0", " ")


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def entry_url(e):
    for l in e.get("link", []):
        if l.get("rel") == "alternate":
            return l.get("href", "")
    return ""


def entry_labels(e):
    return [c.get("term", "") for c in e.get("category", [])]


def entry_content(e):
    return (e.get("content") or e.get("summary") or {}).get("$t", "")


def entry_image(e):
    t = e.get("media$thumbnail", {}).get("url", "")
    if t:
        return re.sub(r"/s\d+(-c)?/", "/s800/", t)
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', entry_content(e), re.I)
    return m.group(1) if m else ""


def field(text, names):
    m = re.search(r"(?im)^\s*\[?(?:%s)\]?\s*[:\-]\s*(.+?)\s*$" % "|".join(names), text)
    return m.group(1).strip() if m else ""


def label_to_name(label):
    return re.sub(r"[-_]+", " ", re.sub(r"^Novel[-:]", "", label, flags=re.I)).strip()


def chapter_number(title):
    m = re.search(r"(?i)\b(?:chapter|chap|ch)\.?\s*#?\s*(\d+(?:\.\d+)?)", title or "")
    return float(m.group(1)) if m else None


def fmt_num(n):
    return str(int(n)) if n == int(n) else str(n)


def novel_info_from_page(e):
    text = to_text(entry_content(e))
    nid = field(text, ["novel id", "id", "novel"])
    if not nid:
        return None                                 # About / Contact / etc.
    desc = ""
    m = re.search(r"(?is)(?:^|\n)\s*\[?description\]?\s*[:\-]?\s*(.+)$", text)
    if m:
        desc = re.split(r"(?im)\n\s*\[?(?:novel id|author|original author|translator|editor|status|genres?|language|country|cover url|cover)\]?\s*[:\-]", m.group(1))[0].strip()
    cover = field(text, ["cover url", "cover"]) or entry_image(e)
    return {
        "id": nid, "title": e.get("title", {}).get("$t", ""), "url": entry_url(e),
        "author": field(text, ["original author", "author"]),
        "translator": field(text, ["translator"]),
        "status": field(text, ["status"]),
        "genres": field(text, ["genres", "genre"]),
        "language": field(text, ["language"]),
        "cover": cover, "desc": desc,
    }


def build_novel_index(page_entries):
    idx = {}
    for e in page_entries:
        info = novel_info_from_page(e)
        if info:
            idx[norm(info["id"])] = info
            idx[norm(re.sub(r"^Novel[-:]", "", info["id"], flags=re.I))] = info
            idx[norm(info["title"])] = info
    return idx


def find_novel(idx, label):
    return (idx.get(norm(label)) or idx.get(norm(label_to_name(label))) or {})


def cut(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"


def send(webhook, payload):
    payload.setdefault("username", BOT_NAME)
    if BOT_AVATAR:
        payload.setdefault("avatar_url", BOT_AVATAR)
    if DRY_RUN:
        log("[DRY RUN]", json.dumps(payload, ensure_ascii=False)[:900])
        return True
    code, body = http(webhook, payload)
    ok = code in (200, 204)
    if not ok:
        log("Discord error", code, body[:300])
    time.sleep(1.2)
    return ok


def ping(role, text):
    if role:
        return {"content": f"<@&{role}> {text}", "allowed_mentions": {"parse": [], "roles": [role]}}
    return {"content": text, "allowed_mentions": {"parse": []}}


# ------------------------------ chapters --------------------------------------
def chapter_payload(label, items, novel):
    name = novel.get("title") or label_to_name(label)
    novel_url = novel.get("url", "")
    role = ROLE_MAP.get(label) or CHAPTER_ROLE
    nums = [chapter_number(i["title"]) for i in items]
    miles = []
    if MILESTONE_EVERY:
        miles = [n for n in nums if n and n == int(n) and int(n) % MILESTONE_EVERY == 0]

    emb = {"color": EMBED_COLOR, "author": {"name": name, "url": novel_url} if novel_url else {"name": name}}
    if novel.get("cover"):
        emb["thumbnail"] = {"url": novel["cover"]}
    elif items[-1]["image"]:
        emb["thumbnail"] = {"url": items[-1]["image"]}
    fields = []
    if novel.get("status"):
        fields.append({"name": "Status", "value": cut(novel["status"], 60), "inline": True})
    if novel.get("genres"):
        fields.append({"name": "Genres", "value": cut(novel["genres"], 100), "inline": True})

    if len(items) == 1:
        it = items[0]
        emb["title"] = cut(it["title"], 250)
        emb["url"] = it["url"]
        if it["minutes"]:
            fields.append({"name": "Read time", "value": f"~{it['minutes']} min", "inline": True})
        emb["timestamp"] = it["published"]
        head = "has a new chapter!"
        text = f"**{name}** {head}"
    else:
        first, last = nums[0], nums[-1]
        span = f" (Ch. {fmt_num(first)}\u2013{fmt_num(last)})" if first and last else ""
        emb["title"] = cut(f"{len(items)} new chapters{span}", 250)
        emb["url"] = items[-1]["url"]
        lines = [f"\u2022 [{cut(i['title'], 80)}]({i['url']})" for i in items[:MAX_LIST]]
        if len(items) > MAX_LIST:
            lines.append(f"\u2026and {len(items) - MAX_LIST} more")
        emb["description"] = "\n".join(lines)
        emb["timestamp"] = items[-1]["published"]
        text = f"**{name}** just got {len(items)} new chapters!"
    if fields:
        emb["fields"] = fields
    emb["footer"] = {"text": f"{SITE_NAME} \u2022 Happy reading!"}
    if miles:
        text += f"\n\U0001F389 **Milestone: Chapter {fmt_num(max(miles))}!** Thank you for reading!"
    p = ping(role, text)
    p["embeds"] = [emb]
    return p


def make_items(entries):
    out = []
    for e in entries:
        labels = [l for l in entry_labels(e) if re.match(r"(?i)^novel[-:]", l)]
        if not labels:
            continue
        txt = to_text(entry_content(e))
        words = len(txt.split())
        out.append({
            "id": e.get("id", {}).get("$t", ""), "label": labels[0],
            "title": to_text(e.get("title", {}).get("$t", "")).strip(),
            "url": entry_url(e), "published": e.get("published", {}).get("$t", ""),
            "image": entry_image(e),
            "minutes": max(1, round(words / 200)) if words >= 150 else 0,
        })
    out.sort(key=lambda x: x["published"])
    return out


# ------------------------------ novels ----------------------------------------
def novel_payload(info):
    emb = {"color": EMBED_COLOR, "title": cut(info["title"], 250), "url": info["url"],
           "description": cut(info["desc"], 600) or "A new novel has been added.",
           "footer": {"text": f"{SITE_NAME} \u2022 New novel"}}
    if info["cover"]:
        emb["image"] = {"url": info["cover"]}
    f = []
    for k, v in (("Status", info["status"]), ("Genres", info["genres"]),
                 ("Author", info["author"]), ("Translator", info["translator"]),
                 ("Language", info["language"])):
        if v:
            f.append({"name": k, "value": cut(v, 100), "inline": True})
    if f:
        emb["fields"] = f
    p = ping(NOVEL_ROLE, "**A new novel just arrived!**")
    p["embeds"] = [emb]
    return p


# ------------------------------- state ----------------------------------------
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(st):
    if DRY_RUN:
        return
    st["posts"] = st["posts"][-600:]
    st["pages"] = st["pages"][-300:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)


def main():
    if not CHAPTER_WEBHOOK and not DRY_RUN:
        log("ERROR: CHAPTER_WEBHOOK secret is missing.")
        return 1
    posts = get_feed("posts")
    pages = get_feed("pages")
    items = make_items(posts)
    novel_idx = build_novel_index(pages)
    state = load_state()

    # first ever run: remember what already exists, post nothing
    if state is None and not TEST_LATEST:
        state = {"posts": [i["id"] for i in items],
                 "pages": [norm(i["id"]) for i in novel_idx.values()],
                 "version": 1}
        state["pages"] = sorted(set(state["pages"]))
        save_state(state)
        log(f"First run: baseline saved ({len(state['posts'])} chapters, {len(state['pages'])} novels). Nothing sent.")
        return 0
    if state is None:
        state = {"posts": [], "pages": [], "version": 1}

    failed = False
    seen_posts, seen_pages = set(state["posts"]), set(state["pages"])

    if TEST_LATEST and items:
        new_items = [items[-1]]
    else:
        new_items = [i for i in items if i["id"] not in seen_posts]

    groups = {}
    for it in new_items:
        groups.setdefault(it["label"], []).append(it)
    for label, its in groups.items():
        ok = send(CHAPTER_WEBHOOK, chapter_payload(label, its, find_novel(novel_idx, label)))
        if ok:
            if not TEST_LATEST:
                state["posts"] += [i["id"] for i in its]
        else:
            failed = True
    log(f"Chapters: {len(new_items)} new")

    seen_novels, seen_keys = 0, set()
    for info in novel_idx.values():
        key = norm(info["id"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key in seen_pages:
            continue
        if NOVEL_WEBHOOK and not TEST_LATEST:
            if send(NOVEL_WEBHOOK, novel_payload(info)):
                state["pages"].append(key); seen_novels += 1
            else:
                failed = True
        elif not NOVEL_WEBHOOK:
            state["pages"].append(key)              # no webhook yet: don't spam old novels later
    log(f"Novels: {seen_novels} announced")

    save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
