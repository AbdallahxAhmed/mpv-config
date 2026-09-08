"""Opt-in, one-file toolbar upgrade. Preview is the default; never touches mpv.conf."""
import argparse
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid

OLD_CONTROLS = 'menu,gap,subtitles,audio,<stream>stream-quality,command:graphic_eq:keypress F8?Stable Volume,gap,fullscreen'
PREVIOUS_CONTROLS = OLD_CONTROLS + ',gap,command:content_paste:script-binding smart_paste/paste-to-open?Paste link (Ctrl+V),<user-data/mpv/ytdl/is-youtube>command:closed_caption:script-binding ytdl_sub_menu/open?YouTube captions (Ctrl+C)'
ICON_FIRST_V1_CONTROLS = 'menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,gap,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,command:headphones:script-binding uosc/audio?Audio tracks and dubs,<stream>stream-quality?Video quality,gap,button:stable-volume,space,fullscreen'
ICON_FIRST_V2_CONTROLS = 'menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,gap,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,command:headphones:script-binding uosc/audio?Audio tracks and dubs,<stream>button:stream-quality,gap,button:stable-volume,space,fullscreen'
ICON_FIRST_V3_CONTROLS = 'menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,gap,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<stream>button:stream-quality,gap,button:stable-volume,space,fullscreen'
ICON_FIRST_V4_CONTROLS = 'menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,gap,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,gap,button:audio-tracks,gap,<stream>button:stream-quality,gap,button:stable-volume,space,fullscreen'
NEW_CONTROLS = 'menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<stream>button:stream-quality,button:stable-volume,loop-file,space,fullscreen'
ACCEPTED_CONTROLS = (OLD_CONTROLS, PREVIOUS_CONTROLS, ICON_FIRST_V1_CONTROLS, ICON_FIRST_V2_CONTROLS, ICON_FIRST_V3_CONTROLS, ICON_FIRST_V4_CONTROLS)
REQUIRED_SCRIPTS = (
    "scripts/smart-paste.lua", "scripts/ytdl-sub-menu.lua", "scripts/ytdl_hook.lua",
    "scripts/modules/stream_policy.lua", "scripts/player-toolbar.lua",
    "tools/vtt_translate.py",
)
DEFAULTS = {'controls_size': (('44',), '32'), 'controls_spacing': (('2', '4', '8'), '10'),
            'controls_persistency': (('',), 'idle'), 'menu_item_height': (('36',), '44'),
            'menu_min_width': (('260',), '300'), 'menu_padding': (('4',), '6')}

def plan(raw):
    lines = raw.decode('utf-8').splitlines(keepends=True)
    settings = {}
    for i, line in enumerate(lines):
        body = line.lstrip('\ufeff \t').rstrip('\r\n')
        if body.startswith('#') or '=' not in body:
            continue
        key, value = body.split('=', 1)
        settings.setdefault(key.strip(), []).append((i, value.strip()))
    for key in ('controls', *DEFAULTS):
        if len(settings.get(key, [])) > 1:
            raise ValueError('Ambiguous repeated setting: ' + key)
    controls = settings.get('controls', [])
    if not controls or controls[0][1] not in (*ACCEPTED_CONTROLS, NEW_CONTROLS):
        raise ValueError('Custom or missing toolbar; use the manual layout instructions instead')
    changes = []
    for key, (old, new) in {'controls': (OLD_CONTROLS, NEW_CONTROLS), **DEFAULTS}.items():
        current = settings.get(key, [])
        accepted = ACCEPTED_CONTROLS if key == "controls" else old if isinstance(old, tuple) else (old,)
        if not current or current[0][1] not in accepted or current[0][1] == new:
            continue
        i = current[0][0]
        line = lines[i]
        ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        leading = line[:len(line) - len(line.lstrip('\ufeff \t'))]
        lines[i] = leading + key + '=' + new + ending
        changes.append(key)
    return ''.join(lines).encode('utf-8'), changes

def _validate(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Refusing a symlinked uosc.conf or script-opts directory')
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('Expected an existing regular uosc.conf smaller than 1 MiB')

def upgrade(config_dir, *, apply=False):
    path = Path(config_dir).expanduser().absolute() / 'script-opts' / 'uosc.conf'
    _validate(path)
    raw = path.read_bytes()
    updated, changes = plan(raw)
    if not changes or not apply:
        return changes, None
    if 'controls' in changes:
        missing = [name for name in REQUIRED_SCRIPTS if not (path.parent.parent / name).is_file()]
        if missing:
            raise ValueError('Update GUI scripts before applying this toolbar: ' + ', '.join(missing))
    mode = stat.S_IMODE(path.stat().st_mode)
    backup = path.with_name(path.name + '.pre-youtube-' + uuid.uuid4().hex + '.bak')
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    fd, name = tempfile.mkstemp(prefix='.uosc-youtube-', dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(updated)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, mode)
        _validate(path)
        if path.read_bytes() != raw:
            raise ValueError('uosc.conf changed during upgrade; original backup retained')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return changes, backup

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', required=True, help='Your active mpv configuration directory')
    parser.add_argument('--apply', action='store_true', help='Apply after making a unique backup; otherwise preview only')
    args = parser.parse_args(argv)
    try:
        changes, backup = upgrade(args.config_dir, apply=args.apply)
    except (OSError, ValueError, UnicodeError) as error:
        parser.error(str(error))
    if not changes:
        print('Already configured; no files changed.')
    elif backup:
        print('Updated: ' + ', '.join(changes))
        print('Backup: ' + str(backup))
    else:
        print('Preview only: ' + ', '.join(changes))
        print('No files changed. Close mpv and add --apply to install these changes.')

    if args.apply:
        cfg = Path(args.config_dir).expanduser().absolute()
        repo_root = Path(__file__).resolve().parents[1]
        synced = []
        for script_rel in REQUIRED_SCRIPTS:
            src = repo_root / script_rel
            dst = cfg / script_rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                synced.append(str(script_rel))
        legacy_script = cfg / "scripts" / "vtt_translate.py"
        if legacy_script.is_file():
            legacy_script.unlink()
        if synced:
            print('Synced scripts: ' + ', '.join(synced))

if __name__ == '__main__':
    main()
