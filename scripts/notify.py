#!/usr/bin/env python3
"""Send an HTML-formatted CI notification without logging credentials."""
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def message(env, metadata=None):
    status = env['BUILD_STATUS']
    exists = env.get('BUILD_EXISTS', '')
    if status == 'started':
        title = 'LineageOS kebab: build check started'
    elif status == 'success' and exists == 'yes':
        title = 'LineageOS kebab: no new build to publish'
    elif status == 'success':
        title = 'LineageOS kebab: build and release succeeded'
    else:
        title = 'LineageOS kebab: workflow ' + status
    esc = html.escape
    lines = ['<b>' + esc(title) + '</b>']
    if metadata:
        lines.extend(['', '<b>ROM</b>\n<code>' + esc(metadata['rom']['filename']) + '</code>',
                      '<b>Stock boot SHA-256</b>\n<code>' + esc(metadata['boot']['sha256']) + '</code>',
                      '<b>Kernel</b>\n<code>' + esc(metadata['kernel_commit']) + '</code>',
                      '<b>BakaSU</b>\n<code>' + esc(metadata['bakasu_commit']) + '</code>'])
        if status == 'success' and exists == 'no':
            lines.append('\n<i>Offline verified only; not device tested. AVB NONE; unlocked bootloader required.</i>')
            url = 'https://github.com/' + env['GITHUB_REPOSITORY'] + '/releases/tag/kebab-' + metadata['identity']
            lines.append('<a href="' + esc(url, quote=True) + '">View release</a>')
    elif env.get('BUILD_DATE'):
        lines.append('Requested date: <code>' + esc(env['BUILD_DATE']) + '</code>')
    url = env['GITHUB_SERVER_URL'] + '/' + env['GITHUB_REPOSITORY'] + '/actions/runs/' + env['GITHUB_RUN_ID']
    lines.append('<a href="' + esc(url, quote=True) + '">View workflow run</a>')
    return '\n'.join(lines)


def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        raise SystemExit('Telegram notification not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets')
    p = Path('selection/inputs.json')
    metadata = json.loads(p.read_text()) if p.exists() else None
    payload = urllib.parse.urlencode({'chat_id': chat, 'text': message(os.environ, metadata),
                                     'parse_mode': 'HTML',
                                     'disable_notification': 'true' if os.environ['BUILD_STATUS'] in ('started', 'success') else 'false'}).encode()
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage', data=payload)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        if result.get('ok') is not True:
            raise ValueError('Telegram returned an unsuccessful response')
    except (urllib.error.URLError, ValueError, OSError):
        # urllib exceptions can contain the request URL and therefore the token.
        raise SystemExit('Telegram notification failed; check bot, chat ID and network') from None
    print('Telegram notification sent')


if __name__ == '__main__':
    main()
