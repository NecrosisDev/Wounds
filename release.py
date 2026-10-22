"""Builds the two mods in this repository for release, each into its own dist folder:

    Injuries         dist/mods/com.necrosis.injuries/                 dist/Injuries-<version>.zip
    Ground Fighters  crawlers/dist/mods/com.necrosis.groundfighters/  crawlers/dist/GroundFighters-<version>.zip

    python -X utf8 -B release.py [--zip-only] [--tag injuries-v<version> | groundfighters-v<version>]

A mod is its manifest.toml and scripts/ folder (Ground Fighters' clips.bin is authored by
crawlers/tools/make_clips.py and kept in scripts/). Each ZIP holds mods/<id>/ as EMTK loads it from the Exanima
folder, with a .sha256 beside it; its entries carry a fixed timestamp, so the same files always give the same
SHA256. Before building, the previous mod folder is moved to dist/previous/, so the ZIP holds only what this build
wrote. --zip-only packages the mod folders as they stand. --tag builds only the mod it names and stops unless its
version matches the manifest's.
"""
import argparse
import hashlib
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODS = {
    'injuries': ('Injuries', 'com.necrosis.injuries', ROOT),
    'groundfighters': ('GroundFighters', 'com.necrosis.groundfighters', ROOT / 'crawlers'),
}


def assemble(source: Path, mod: Path) -> None:
    shutil.copytree(source / 'scripts', mod / 'scripts')
    shutil.copyfile(source / 'manifest.toml', mod / 'manifest.toml')


def version(mod: Path) -> str:
    match = re.search(r'^version = "([^"]+)"', (mod / 'manifest.toml').read_text(encoding='utf-8'), re.M)
    if not match:
        raise SystemExit(f'{mod / "manifest.toml"} has no version line')
    return match.group(1)


def set_aside(mod: Path) -> None:
    if mod.exists():
        target = mod.parents[1] / 'previous' / f'{mod.name}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}'
        target.parent.mkdir(parents=True, exist_ok=True)
        mod.rename(target)
        print(f'previous build moved to {target}')


def package(mod: Path, name: str) -> Path:
    files = sorted(p for p in mod.rglob('*') if p.is_file())
    archive = mod.parents[1] / f'{name}-{version(mod)}.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for path in files:
            info = zipfile.ZipInfo(f'mods/{mod.name}/{path.relative_to(mod).as_posix()}', date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + '.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'RELEASE={archive} files={len(files)} sha256={digest}')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--zip-only', action='store_true', help='package the mod folders already in dist/')
    parser.add_argument('--tag', help='release tag; must be <mod>-v<manifest version>')
    args = parser.parse_args()
    keys = list(MODS)
    if args.tag:
        key = args.tag.partition('-v')[0]
        if key not in MODS:
            parser.error(f'tag {args.tag} names none of: ' + ', '.join(f'{k}-v<version>' for k in MODS))
        keys = [key]
    for key in keys:
        name, mod_id, source = MODS[key]
        mod = source / 'dist' / 'mods' / mod_id
        if not args.zip_only:
            set_aside(mod)
            assemble(source, mod)
        if not (mod / 'manifest.toml').is_file():
            raise SystemExit(f'no built mod in {mod}')
        if args.tag and args.tag != f'{key}-v{version(mod)}':
            raise SystemExit(f'tag {args.tag} does not match manifest version {version(mod)}')
        package(mod, name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
