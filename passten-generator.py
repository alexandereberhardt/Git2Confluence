#!/usr/bin/env python3
"""passten-generator.py - Generate PASSTEN documentation from GitLab repos.

Usage:
    python3 passten-generator.py generate --solution GFS
    python3 passten-generator.py extract --solution GFS --output extraction.json
    python3 passten-generator.py publish --input passten-pages-full.json --solution GFS
"""
import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from passten.config import load_config, get_solution
from passten.extractor import GitLabExtractor
from passten.synthesizer import Synthesizer
from passten.publisher import ConfluencePublisher, AUTO_GENERATED_MARKER
from passten.templates import PASSTEN_HIERARCHY, get_section, SECTIONS, build_hierarchy

DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, 'passten-config.yaml')


def _read_glab_token(host: str) -> str | None:
    """Read GitLab token from glab CLI config."""
    import yaml
    config_path = os.path.expanduser('~/Library/Application Support/glab-cli/config.yml')
    if not os.path.isfile(config_path):
        config_path = os.path.expanduser('~/.config/glab-cli/config.yml')
    if not os.path.isfile(config_path):
        return None
    with open(config_path) as f:
        config = yaml.safe_load(f)
    hosts = config.get('hosts', {})
    host_config = hosts.get(host, {})
    return host_config.get('token')


def extract(solution_name: str, config_path: str = DEFAULT_CONFIG) -> dict:
    config = load_config(config_path)
    solution = get_solution(config, solution_name)

    token = os.environ.get('GITLAB_TOKEN')
    if not token:
        token = _read_glab_token(solution['gitlab_host'])
    if not token:
        print("ERROR: GITLAB_TOKEN not set and no glab token found.")
        sys.exit(1)

    extractor = GitLabExtractor(host=solution['gitlab_host'], token=token)
    extraction = {'solution': solution_name, 'products': {}}

    for product_name, product_config in solution['products'].items():
        print(f"\n=== Extracting product: {product_name} ===")
        if 'subgroup_id' in product_config:
            repos = extractor.discover_repos_by_subgroup(product_config['subgroup_id'])
        else:
            repos = extractor.discover_repos(solution['gitlab_group_id'], product_config)

        print(f"  Found {len(repos)} active repos")
        scanned = []
        for repo in repos:
            ns = repo.get('path_with_namespace', '')
            print(f"  Scanning {ns}...")
            scanned.append(extractor.scan_repo(repo))

        extraction['products'][product_name] = {'repos': scanned}

    return extraction


def synthesize(extraction: dict, config: dict, solution_name: str) -> dict:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    synth = Synthesizer(api_key=api_key)
    all_repos = []
    for product in extraction['products'].values():
        all_repos.extend(product['repos'])

    hierarchy = build_hierarchy(solution_name)
    titles_needed = _collect_titles(hierarchy)

    pages = {}
    for title in titles_needed:
        section = get_section(title)
        if not section:
            section = get_section('Digital Solution Home') if title.endswith('Digital Solution Home') else None
        if not section:
            print(f"  Skipping: {title} (no section definition)")
            continue
        print(f"  Generating: {title}...")
        if section.placeholder:
            pages[title] = synth.generate_placeholder(section)
        else:
            pages[title] = synth.synthesize_section(section, {'repos': all_repos})

    return pages


def _collect_titles(node: dict) -> list[str]:
    """Recursively collect all titles from the hierarchy tree."""
    titles = [node['title']]
    for child in node.get('children', []):
        titles.extend(_collect_titles(child))
    return titles


def _confluence_title(title: str) -> str:
    return title


def publish(pages: dict, config: dict, solution_name: str):
    solution = get_solution(config, solution_name)
    space_key = solution['confluence_space']
    root_parent_id = solution['confluence_parent_id']

    pub = ConfluencePublisher()
    pub._initialize()

    hierarchy = build_hierarchy(solution_name)
    created_ids = {}

    def publish_node(node: dict, parent_id: str):
        title = node['title']
        confluence_title = _confluence_title(title)
        body = pages.get(title, '')
        print(f"  Publishing: {confluence_title}")
        result = pub.upsert_page(space_key=space_key, parent_id=parent_id,
                                 title=confluence_title, body=body)
        page_id = result.get('id', '')
        created_ids[title] = page_id
        for child in node.get('children', []):
            publish_node(child, page_id)

    publish_node(hierarchy, root_parent_id)
    print(f"\n  Published {len(created_ids)} pages.")
    return created_ids


def cmd_generate(args):
    print(f"=== PASSTEN Generator: Full Pipeline for {args.solution} ===")
    extraction = extract(args.solution, args.config)
    config = load_config(args.config)
    print("\n=== Synthesizing documentation ===")
    pages = synthesize(extraction, config, args.solution)
    print("\n=== Publishing to Confluence ===")
    publish(pages, config, args.solution)
    print("\n=== Done ===")


def cmd_extract(args):
    print(f"=== PASSTEN Generator: Extract for {args.solution} ===")
    extraction = extract(args.solution, args.config)
    output_path = args.output or f"{args.solution.lower()}-extraction.json"
    with open(output_path, 'w') as f:
        json.dump(extraction, f, indent=2)
    print(f"\nExtraction saved to {output_path}")


def cmd_publish(args):
    """Publish pre-generated pages JSON to Confluence."""
    print(f"=== PASSTEN Generator: Publish from {args.input} ===")
    with open(args.input) as f:
        data = json.load(f)
    # Support both pages.json (title->html map) and extraction.json (with synthesis)
    if 'solution' in data and 'products' in data:
        solution_name = data['solution']
        config = load_config(args.config)
        print("\n=== Synthesizing documentation ===")
        pages = synthesize(data, config, solution_name)
    else:
        # Direct pages map: {"title": "html_content", ...}
        solution_name = args.solution or 'GFS'
        config = load_config(args.config)
        pages = data
    print("\n=== Publishing to Confluence ===")
    publish(pages, config, solution_name)
    print("\n=== Done ===")


def main():
    parser = argparse.ArgumentParser(description='PASSTEN Documentation Generator')
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='Path to config YAML')
    subparsers = parser.add_subparsers(dest='command', required=True)

    gen_parser = subparsers.add_parser('generate', help='Full pipeline: extract + synthesize + publish')
    gen_parser.add_argument('--solution', required=True, help='Solution name (e.g., GFS)')

    ext_parser = subparsers.add_parser('extract', help='Extract only')
    ext_parser.add_argument('--solution', required=True, help='Solution name')
    ext_parser.add_argument('--output', help='Output JSON path')

    pub_parser = subparsers.add_parser('publish', help='Publish pages to Confluence')
    pub_parser.add_argument('--input', required=True, help='Pages JSON (title->html map) or extraction JSON')
    pub_parser.add_argument('--solution', default='GFS', help='Solution name (for pages JSON)')

    args = parser.parse_args()
    {'generate': cmd_generate, 'extract': cmd_extract, 'publish': cmd_publish}[args.command](args)


if __name__ == '__main__':
    main()
