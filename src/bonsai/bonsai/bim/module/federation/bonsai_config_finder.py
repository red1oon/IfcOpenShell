#!/usr/bin/env python3
"""
Bonsai Development Configuration Finder
Scans your IfcOpenShell project for useful development settings and scripts

Usage:
    python bonsai_config_finder.py

Output:
    - Found configuration files
    - Useful scripts and their purposes
    - Launch commands for Blender development
    - Environment settings
"""

import os
import json
from pathlib import Path
from typing import Dict, List

class BonsaiConfigFinder:
    """Find and extract Bonsai development configurations"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.findings = {
            'scripts': [],
            'configs': [],
            'makefiles': [],
            'launch_commands': [],
            'environment': []
        }
    
    def scan_all(self):
        """Run all scanning methods"""
        print(f"🔍 Scanning: {self.project_root}\n")
        
        self.find_scripts()
        self.find_makefiles()
        self.find_config_files()
        self.extract_launch_commands()
        self.check_environment()
        
        self.print_report()
    
    def find_scripts(self):
        """Find useful Python scripts in the project"""
        scripts_dir = self.project_root / "src" / "bonsai" / "scripts"
        
        if scripts_dir.exists():
            for script in scripts_dir.glob("*.py"):
                purpose = self._guess_script_purpose(script)
                self.findings['scripts'].append({
                    'path': str(script),
                    'name': script.name,
                    'purpose': purpose
                })
    
    def find_makefiles(self):
        """Find and parse Makefiles"""
        makefile = self.project_root / "src" / "bonsai" / "Makefile"
        
        if makefile.exists():
            targets = self._parse_makefile_targets(makefile)
            self.findings['makefiles'].append({
                'path': str(makefile),
                'targets': targets
            })
    
    def find_config_files(self):
        """Find configuration files"""
        config_patterns = [
            "*.json",
            "*.toml",
            ".env*",
            "*config*",
            ".vscode/**/*",
            "pyproject.toml",
            "setup.py"
        ]
        
        for pattern in config_patterns:
            for config_file in self.project_root.rglob(pattern):
                # Skip build directories and caches
                if any(skip in str(config_file) for skip in ['build', '__pycache__', 'node_modules', '.git']):
                    continue
                
                self.findings['configs'].append({
                    'path': str(config_file),
                    'type': config_file.suffix
                })
    
    def extract_launch_commands(self):
        """Extract useful launch commands"""
        # From Makefile
        makefile = self.project_root / "src" / "bonsai" / "Makefile"
        if makefile.exists():
            content = makefile.read_text()
            
            # Extract blender commands
            for line in content.split('\n'):
                if 'blender' in line.lower() and not line.strip().startswith('#'):
                    self.findings['launch_commands'].append({
                        'source': 'Makefile',
                        'command': line.strip()
                    })
    
    def check_environment(self):
        """Check current environment settings"""
        env_vars = {
            'BLENDER_USER_SCRIPTS': os.getenv('BLENDER_USER_SCRIPTS'),
            'PYTHONPATH': os.getenv('PYTHONPATH'),
            'PATH': os.getenv('PATH', '').split(':') if os.name != 'nt' else os.getenv('PATH', '').split(';')
        }
        
        self.findings['environment'] = env_vars
    
    def _guess_script_purpose(self, script: Path) -> str:
        """Guess script purpose from name and content"""
        name_lower = script.name.lower()
        
        purposes = {
            'reregister': 'Reload Bonsai addon in Blender',
            'setup': 'Setup development environment',
            'test': 'Run tests',
            'build': 'Build addon package',
            'install': 'Install dependencies',
            'get_wheels': 'Download Python wheels for distribution'
        }
        
        for keyword, purpose in purposes.items():
            if keyword in name_lower:
                return purpose
        
        # Read first few lines for clues
        try:
            content = script.read_text()
            if 'register' in content.lower() and 'addon' in content.lower():
                return 'Addon registration/loading'
            if 'pytest' in content.lower():
                return 'Test runner'
        except:
            pass
        
        return 'Unknown - check file content'
    
    def _parse_makefile_targets(self, makefile: Path) -> List[str]:
        """Extract targets from Makefile"""
        targets = []
        content = makefile.read_text()
        
        for line in content.split('\n'):
            # Match target definitions (word followed by colon)
            if ':' in line and not line.startswith('\t') and not line.startswith('#'):
                target = line.split(':')[0].strip()
                if target and not target.startswith('.'):
                    targets.append(target)
        
        return targets
    
    def print_report(self):
        """Print formatted report"""
        print("=" * 70)
        print("📋 BONSAI DEVELOPMENT CONFIGURATION REPORT")
        print("=" * 70)
        
        # Scripts
        if self.findings['scripts']:
            print("\n🔧 USEFUL SCRIPTS:")
            for script in self.findings['scripts']:
                print(f"  • {script['name']}")
                print(f"    Purpose: {script['purpose']}")
                print(f"    Path: {script['path']}")
                print()
        
        # Makefile targets
        if self.findings['makefiles']:
            print("🎯 MAKEFILE TARGETS:")
            for makefile in self.findings['makefiles']:
                print(f"  File: {makefile['path']}")
                print(f"  Available targets:")
                for target in makefile['targets'][:10]:  # First 10
                    print(f"    - make {target}")
                print()
        
        # Launch commands
        if self.findings['launch_commands']:
            print("🚀 BLENDER LAUNCH COMMANDS:")
            seen = set()
            for cmd in self.findings['launch_commands']:
                if cmd['command'] not in seen:
                    print(f"  {cmd['command']}")
                    seen.add(cmd['command'])
            print()
        
        # Quick reference
        print("📖 QUICK REFERENCE:")
        print("  Reload addon after code changes:")
        print("    cd ~/Projects/IfcOpenShell/src/bonsai")
        print("    make register")
        print()
        print("  Launch Blender manually:")
        print("    blender")
        print()
        print("  Launch with specific IFC file:")
        print("    blender /path/to/file.ifc")
        print()
        print("  Launch with Python console (debugging):")
        print("    blender --python-console")
        print()
        print("  Run unit tests:")
        print("    cd ~/Projects/IfcOpenShell/src/bonsai")
        print("    make test")
        print()
        
        # Environment
        print("🌍 ENVIRONMENT:")
        blender_path = os.popen('which blender').read().strip()
        if blender_path:
            print(f"  Blender executable: {blender_path}")
        else:
            print("  ⚠️  Blender not found in PATH")
        print()
        
        # MEP module location
        mep_module = self.project_root / "src" / "bonsai" / "bonsai" / "bim" / "module" / "mep_engineering"
        if mep_module.exists():
            print("📍 YOUR MEP MODULE:")
            print(f"  {mep_module}")
            files = list(mep_module.glob("*.py"))
            print(f"  Files: {len(files)}")
            for f in files:
                print(f"    - {f.name}")
        
        print("\n" + "=" * 70)


def main():
    """Main entry point"""
    # Detect project root
    current = Path.cwd()
    
    # Try to find IfcOpenShell root
    if 'IfcOpenShell' in str(current):
        project_root = current
        while project_root.name != 'IfcOpenShell' and project_root.parent != project_root:
            project_root = project_root.parent
    else:
        project_root = Path.home() / "Projects" / "IfcOpenShell"
    
    if not project_root.exists():
        print(f"❌ Could not find project root: {project_root}")
        print("\nPlease run this script from your IfcOpenShell directory or")
        print("specify the path as an argument:")
        print("  python bonsai_config_finder.py /path/to/IfcOpenShell")
        return
    
    finder = BonsaiConfigFinder(project_root)
    finder.scan_all()


if __name__ == "__main__":
    main()
