#!/usr/bin/env python3
"""
Setup and Validation Script for Mixed-Precision FFT Optimization
Checks dependencies, creates directories, and validates configuration
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


class SetupValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_failed = 0
    
    def check_python_version(self):
        """Check Python version"""
        print("Checking Python version...", end=" ")
        version = sys.version_info
        if version.major >= 3 and version.minor >= 8:
            print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
            self.checks_passed += 1
            return True
        else:
            print(f"✗ Python {version.major}.{version.minor}.{version.micro}")
            self.errors.append(
                f"Python 3.8+ required, found {version.major}.{version.minor}"
            )
            self.checks_failed += 1
            return False
    
    def check_python_packages(self):
        """Check required Python packages"""
        print("\nChecking Python packages:")
        
        required_packages = {
            'numpy': 'numpy',
            'pymoo': 'pymoo',
            'matplotlib': 'matplotlib',
            'scipy': 'scipy'
        }
        
        all_present = True
        for display_name, import_name in required_packages.items():
            try:
                __import__(import_name)
                print(f"  ✓ {display_name}")
                self.checks_passed += 1
            except ImportError:
                print(f"  ✗ {display_name} - NOT FOUND")
                self.errors.append(f"Missing package: {display_name}")
                all_present = False
                self.checks_failed += 1
        
        return all_present
    
    def check_vivado(self):
        """Check Vivado installation"""
        print("\nChecking Vivado installation:")
        
        # Import config to get Vivado path
        try:
            from globalVariablesMixedFFT import VIVADO_PATH
            
            if os.path.exists(VIVADO_PATH):
                print(f"  ✓ Vivado found at: {VIVADO_PATH}")
                self.checks_passed += 1
                
                # Try to get version
                try:
                    result = subprocess.run(
                        [VIVADO_PATH, '-version'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        version_line = result.stdout.split('\n')[0]
                        print(f"  ✓ {version_line}")
                        self.checks_passed += 1
                    else:
                        print(f"  ⚠ Could not determine Vivado version")
                        self.warnings.append("Vivado version check failed")
                except Exception as e:
                    print(f"  ⚠ Could not check Vivado version: {e}")
                    self.warnings.append("Vivado version check failed")
                
                return True
            else:
                print(f"  ✗ Vivado not found at: {VIVADO_PATH}")
                self.errors.append(
                    "Update VIVADO_PATH in globalVariablesMixedFFT.py"
                )
                self.checks_failed += 1
                return False
        except ImportError:
            print("  ✗ Could not import configuration")
            self.errors.append("Configuration file missing")
            self.checks_failed += 1
            return False
    
    def check_simulator(self):
        """Check Verilog simulator"""
        print("\nChecking Verilog simulator:")
        
        # Check for Icarus Verilog
        try:
            result = subprocess.run(
                ['iverilog', '-v'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"  ✓ Icarus Verilog found")
                version_line = [l for l in result.stderr.split('\n') if 'version' in l.lower()]
                if version_line:
                    print(f"    {version_line[0].strip()}")
                self.checks_passed += 1
                return True
        except FileNotFoundError:
            pass
        
        # Check for ModelSim
        try:
            result = subprocess.run(
                ['vsim', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"  ✓ ModelSim found")
                self.checks_passed += 1
                return True
        except FileNotFoundError:
            pass
        
        print(f"  ✗ No Verilog simulator found")
        self.errors.append(
            "Install Icarus Verilog (iverilog) or ModelSim"
        )
        self.checks_failed += 1
        return False
    
    def check_verilog_sources(self):
        """Check Verilog source files"""
        print("\nChecking Verilog source files:")
        
        required_files = [
            'adder.v',
            'multiplier.v',
            'twiddle_rom.v',
            'agu.v',
            'memory.v',
            'butterfly.v'
        ]
        
        # Check in uploads directory
        upload_dir = Path('/mnt/user-data/uploads')
        all_present = True
        
        for fname in required_files:
            fpath = upload_dir / fname
            if fpath.exists():
                print(f"  ✓ {fname}")
                self.checks_passed += 1
            else:
                print(f"  ✗ {fname} - NOT FOUND")
                self.warnings.append(f"Verilog file not found: {fname}")
                all_present = False
                self.checks_failed += 1
        
        return all_present
    
    def create_directories(self):
        """Create necessary directories"""
        print("\nCreating directory structure:")
        
        directories = [
            './verilog_sources',
            './generated_designs',
            './vivado_projects',
            './reports',
            './sim',
            './results'
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            print(f"  ✓ {directory}")
            self.checks_passed += 1
        
        return True
    
    def validate_configuration(self):
        """Validate configuration parameters"""
        print("\nValidating configuration:")
        
        try:
            from globalVariablesMixedFFT import (
                POPULATION, GENERATIONS, FFT_SIZES,
                CLOCK_PERIOD, FPGA_DEVICE
            )
            
            # Check reasonable values
            if POPULATION > 0 and POPULATION <= 100:
                print(f"  ✓ Population size: {POPULATION}")
                self.checks_passed += 1
            else:
                print(f"  ⚠ Population size unusual: {POPULATION}")
                self.warnings.append("Check POPULATION value")
            
            if GENERATIONS > 0 and GENERATIONS <= 1000:
                print(f"  ✓ Generations: {GENERATIONS}")
                self.checks_passed += 1
            else:
                print(f"  ⚠ Generations unusual: {GENERATIONS}")
                self.warnings.append("Check GENERATIONS value")
            
            print(f"  ✓ FFT sizes: {FFT_SIZES}")
            print(f"  ✓ Clock period: {CLOCK_PERIOD} ns")
            print(f"  ✓ FPGA device: {FPGA_DEVICE}")
            self.checks_passed += 3
            
            return True
            
        except ImportError as e:
            print(f"  ✗ Configuration error: {e}")
            self.errors.append("Could not validate configuration")
            self.checks_failed += 1
            return False
    
    def run_all_checks(self):
        """Run all validation checks"""
        print("="*60)
        print("Mixed-Precision FFT Optimization - Setup Validation")
        print("="*60)
        
        self.check_python_version()
        self.check_python_packages()
        self.check_vivado()
        self.check_simulator()
        self.check_verilog_sources()
        self.create_directories()
        self.validate_configuration()
        
        # Summary
        print("\n" + "="*60)
        print("Validation Summary")
        print("="*60)
        print(f"Checks passed: {self.checks_passed}")
        print(f"Checks failed: {self.checks_failed}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.errors:
            print("\n❌ ERRORS:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        if not self.errors:
            print("\n✅ Setup validation PASSED!")
            print("\nYou can now run the optimization:")
            print("  python runMixedFFTOptimization.py --mode test")
            return True
        else:
            print("\n❌ Setup validation FAILED!")
            print("\nPlease fix the errors above before running optimization.")
            return False


def install_missing_packages():
    """Attempt to install missing Python packages"""
    print("\nAttempting to install missing packages...")
    
    packages = ['numpy', 'pymoo', 'matplotlib', 'scipy']
    
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', package
            ])


def main():
    """Main setup function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Setup and validate Mixed-Precision FFT Optimization'
    )
    parser.add_argument(
        '--install-packages',
        action='store_true',
        help='Attempt to install missing Python packages'
    )
    
    args = parser.parse_args()
    
    if args.install_packages:
        install_missing_packages()
    
    validator = SetupValidator()
    success = validator.run_all_checks()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
