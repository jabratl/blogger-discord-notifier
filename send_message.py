#!/usr/bin/env python3
"""Send your own message to any Discord channel as the JabraTL bot (webhook)."""
import json, os, sys
import notify

CHANNEL   = os.environ.get("CHANNEL", "general")
PING      = os.environ.get("PING", "none")
STYLE     = os.environ.get("STYLE", "embed")
TITLE     = os.environ.get("TITLE", "").strip()
MESSAGE   = os.environ.get("MESSAGE", "").replace("\\n", "\n").strip()
LINK_URL  = os.environ.get("LINK_URL", "").strip()
IMAGE_URL = os.environ.get("IMAGE_URL", "").strip()

HOOKS = {
    "chapters":              os.environ.get("CHAPTER_WEBHOOK", "").strip(),
    "novels":                os.environ.get("NOVEL_WEBHOOK", "").strip(),
    "general":               os.environ.get("GENERAL_WEBHOOK", "").strip(),
    "rules":                 os.environ.get("RULES_WEBHOOK", "").strip(),
    "server_roles":          os.environ.get("SERVER_ROLES_WEBHOOK", "").strip(),
    "server_announcements":   os.environ.get("SERVER_ANNOUNCEMENTS_WEBHOOK", "").strip(),
    "level":                 os.environ.get("LEVEL_WEBHOOK", "").strip(),
    "novel_lists":           os.environ.get("NOVEL_LISTS_WEBHOOK", "").strip(),
    "novel_roles":           os.environ.get("NOVEL_ROLES_WEBHOOK", "").strip(),
    "off_topic":             os.environ.get("OFF_TOPIC_WEBHOOK", "").strip(),
    "novel_discussions":     os.environ.get("NOVEL_DISCUSSIONS_WEBHOOK", "").strip(),
    "novel_recommendations": os.environ.get("NOVEL_RECOMMENDATIONS_WEBHOOK", "").strip(),
    "novel_request":         os.environ.get("NOVEL_REQUEST_WEBHOOK", "").strip(),
    "spoilers":              os.environ.get("SPOILERS_WEBHOOK", "").strip(),
    "novel_illustration":    os.environ.get("NOVEL_ILLUSTRATION_WEBHOOK", "").strip(),
    "nsfw":                  os.environ.get("NSFW_WEBHOOK", "").strip(),
}

ROLES = {
    "chapter_role": os.environ.get("CHAPTER_ROLE_ID", "").strip(),
    "novel_role":   os.environ.get("NOVEL_ROLE_ID", "").strip()
}

def main():
    hook = HOOKS.get(CHANNEL, "")
    if not hook and not notify.DRY_RUN:
        print(f"ERROR: no webhook secret found for channel '{CHANNEL}'. Check your GitHub Secrets configuration.")
        return 1
    if not MESSAGE:
        print("ERROR: message is empty.")
        return 1
    role = ROLES.get(PING, "")
    if PING != "none" and not role:
        print(f"ERROR: PING={PING} but its role ID secret is missing.")
        return 1

    if STYLE == "embed":
        if len(MESSAGE) > 4000:
            print("ERROR: message too long for an embed (max 4000 characters).")
            return 1
        emb = {
            "color": notify.EMBED_COLOR,
            "description": MESSAGE,
            "footer": {"text": notify.SITE_NAME}
        }
        if TITLE:
            emb["title"] = notify.cut(TITLE, 250)
        if LINK_URL:
            emb["url"] = LINK_URL
        if IMAGE_URL:
            emb["image"] = {"url": IMAGE_URL}
        payload = {"embeds": [emb], "allowed_mentions": {"parse": []}}
        if role:
            payload["content"] = f"<@&{role}>"
            payload["allowed_mentions"] = {"parse": [], "roles": [role]}
    else:
        text = (f"**{TITLE}**\n" if TITLE else "") + MESSAGE
        if LINK_URL:
            text += f"\n{LINK_URL}"
        if len(text) > 1900:
            print("ERROR: message too long for a plain message (max about 1900 characters).")
            return 1
        payload = notify.ping(role, text)
        if IMAGE_URL:
            payload["embeds"] = [{"color": notify.EMBED_COLOR, "image": {"url": IMAGE_URL}}]

    ok = notify.send(hook, payload)
    print("Sent successfully." if ok else "FAILED.")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
