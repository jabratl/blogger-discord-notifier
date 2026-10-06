#!/usr/bin/env python3
"""Send your own message to a Discord channel as the JabraTL bot (webhook)."""
import json, os, sys
import notify                      # re-uses settings + the safe http helper

CHANNEL   = os.environ.get("CHANNEL", "general")        # chapters | novels | general
PING      = os.environ.get("PING", "none")              # none | chapter_role | novel_role
STYLE     = os.environ.get("STYLE", "embed")            # embed | plain
TITLE     = os.environ.get("TITLE", "").strip()
MESSAGE   = os.environ.get("MESSAGE", "").replace("\\n", "\n").strip()
LINK_URL  = os.environ.get("LINK_URL", "").strip()
IMAGE_URL = os.environ.get("IMAGE_URL", "").strip()
HOOKS = {
    "chapters": os.environ.get("CHAPTER_WEBHOOK", "").strip(),
    "novels":   os.environ.get("NOVEL_WEBHOOK", "").strip(),
    "general":  os.environ.get("GENERAL_WEBHOOK", "").strip(),
}
ROLES = {"chapter_role": os.environ.get("CHAPTER_ROLE_ID", "").strip(),
         "novel_role":   os.environ.get("NOVEL_ROLE_ID", "").strip()}


def main():
    hook = HOOKS.get(CHANNEL, "")
    if not hook and not notify.DRY_RUN:
        print(f"ERROR: no webhook secret for channel '{CHANNEL}'. "
              f"(chapters=CHAPTER_WEBHOOK, novels=NOVEL_WEBHOOK, general=GENERAL_WEBHOOK)")
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
        emb = {"color": notify.EMBED_COLOR, "description": MESSAGE,
               "footer": {"text": notify.SITE_NAME}}
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
    print("Sent." if ok else "FAILED.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
