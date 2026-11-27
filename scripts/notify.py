#!/usr/bin/env python3
"""Send a plain-text CI notification without logging bot credentials."""
import json
import os
import sys
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
    lines = [title]
    if metadata:
        lines.extend(['ROM: ' + metadata['rom']['filename'],
                      'Stock boot SHA-256: ' + metadata['boot']['sha256'],
                      'Kernel: ' + metadata['kernel_commit'],
                      'BakaSU: ' + metadata['bakasu_commit']])
        if status == 'success' and exists == 'no':
            lines.append('Offline verified only; not device tested. AVB NONE; unlocked bootloader required.')
            lines.append('Release: https://github.com/' + env['GITHUB_REPOSITORY'] + '/releases/tag/kebab-' + metadata['identity'])
    elif env.get('BUILD_DATE'):
        lines.append('Requested date: ' + env['BUILD_DATE'])
    lines.append('Run: ' + env['GITHUB_SERVER_URL'] + '/' + env['GITHUB_REPOSITORY'] + '/actions/runs/' + env['GITHUB_RUN_ID'])
    return '\n'.join(lines)


def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        raise SystemExit('Telegram notification not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets')
    p = Path('selection/inputs.json')
    metadata = json.loads(p.read_text()) if p.exists() else None
    payload = urllib.parse.urlencode({'chat_id': chat, 'text': message(os.environ, metadata),
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
