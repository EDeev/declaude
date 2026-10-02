"""Command-line interface: declaude --build | --update ZIP | --remap | --map CONV PROJ."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .loader import DataLoader, MappingManager, extract_zip
from .site import SiteBuilder

OUTPUT_DIR = Path("claude_archive")
MAPPING_FILE = Path("mapping.json")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="declaude — Claude backup → static HTML archive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  --build                   Generate full archive from backup directory
  --update path/to/new.zip  Merge new backup zip, regenerate changed pages only
  --remap                   Rebuild index + project pages after editing mapping.json
  --map CONV_UUID PROJ_UUID Assign a conversation to a project in mapping.json

Source options:
  --source PATH             Path to backup directory (default: ./claude-backup-v1)
  --output PATH             Output directory (default: ./claude_archive)
  --mapping PATH            mapping.json path (default: ./mapping.json)

Examples:
  python declaude.py --build
  python declaude.py --build --source ./my-backup --output ./my-archive
  python declaude.py --update new_export.zip
  python declaude.py --remap
  python declaude.py --map abc123 proj456
        """
    )
    parser.add_argument("--build", action="store_true", help="Full build from source")
    parser.add_argument("--update", metavar="ZIP", help="Update from new zip archive")
    parser.add_argument("--remap", action="store_true", help="Rebuild index/project pages after mapping change")
    parser.add_argument("--map", nargs=2, metavar=("CONV_UUID","PROJ_UUID"),
                        help="Assign conversation to project in mapping.json")
    parser.add_argument("--source", default="claude-backup-v1", metavar="PATH",
                        help="Source backup directory (default: claude-backup-v1)")
    parser.add_argument("--output", default=str(OUTPUT_DIR), metavar="PATH",
                        help=f"Output directory (default: {OUTPUT_DIR})")
    parser.add_argument("--mapping", default=str(MAPPING_FILE), metavar="PATH",
                        help=f"Mapping file path (default: {MAPPING_FILE})")

    args = parser.parse_args()

    out_dir = Path(args.output)
    mapping_path = Path(args.mapping)
    source_dir = Path(args.source)

    # Load mapping (always)
    mapping = MappingManager(mapping_path)
    mapping.load()

    # --map: just add one entry and exit
    if args.map:
        conv_uuid, proj_uuid = args.map
        mapping.assign(conv_uuid, proj_uuid)
        mapping.save()
        print(f"Mapped conversation {conv_uuid} -> project {proj_uuid}")
        print(f"Saved to {mapping_path}. Run --remap to rebuild project pages.")
        return

    # --remap: load data, rebuild index + project pages
    if args.remap:
        print(f"Loading data from {source_dir}...")
        loader = DataLoader(source_dir)
        loader.load()
        site = SiteBuilder(out_dir, loader, mapping)
        site.build_remap()
        mapping.save()
        return

    # --update: load existing + new zip, merge
    if args.update:
        zip_path = Path(args.update)
        if not zip_path.exists():
            print(f"Error: {zip_path} not found.")
            sys.exit(1)

        print(f"Loading existing data from {source_dir}...")
        old_loader = DataLoader(source_dir)
        old_loader.load()

        print(f"Extracting {zip_path}...")
        tmp_dir = Path("_declaude_tmp")
        new_source = extract_zip(zip_path, tmp_dir)
        print(f"Loading new data from {new_source}...")
        new_loader = DataLoader(new_source)
        new_loader.load()

        site = SiteBuilder(out_dir, old_loader, mapping)
        site.build_update(new_loader)
        mapping.save()

        # Clean up temp dir
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # --build (default if nothing specified or --build explicit)
    if args.build or not any([args.remap, args.update, args.map]):
        if not source_dir.exists():
            print(f"Error: source directory '{source_dir}' not found.")
            print("Use --source to specify the backup directory.")
            sys.exit(1)
        print(f"Loading data from {source_dir}...")
        loader = DataLoader(source_dir)
        loader.load()
        site = SiteBuilder(out_dir, loader, mapping)
        site.build_all()
        mapping.save()
        return

    parser.print_help()


