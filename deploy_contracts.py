#!/usr/bin/env python3
"""
Script to deploy contracts and update deployment configuration
"""
import json
import subprocess
import sys
from pathlib import Path

def run_command(command):
    """Run a command and return the result"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print("🚀 Deploying updated Certification contract...")
    
    # Step 1: Compile contracts
    print("📦 Compiling contracts...")
    success, stdout, stderr = run_command("truffle compile")
    if not success:
        print(f"❌ Compilation failed: {stderr}")
        return False
    
    # Step 2: Deploy contracts
    print("🔗 Deploying contracts to blockchain...")
    success, stdout, stderr = run_command("truffle migrate --reset")
    if not success:
        print(f"❌ Deployment failed: {stderr}")
        return False
    
    # Step 3: Extract contract addresses
    print("📝 Extracting contract addresses...")
    try:
        # Read the build artifacts
        build_path = Path("build/contracts/Certification.json")
        if not build_path.exists():
            print("❌ Build artifacts not found. Please run 'truffle compile' first.")
            return False
        
        with open(build_path, 'r') as f:
            contract_data = json.load(f)
        
        # Get the network ID (assuming development network)
        networks = contract_data.get('networks', {})
        if not networks:
            print("❌ No deployed networks found. Please ensure Ganache is running.")
            return False
        
        # Get the first network (development)
        network_id = list(networks.keys())[0]
        contract_address = networks[network_id]['address']
        
        # Update deployment config
        deployment_config = {
            "Certification": contract_address
        }
        
        with open("deployment_config.json", 'w') as f:
            json.dump(deployment_config, f, indent=2)
        
        print(f"✅ Contract deployed successfully!")
        print(f"📋 Contract Address: {contract_address}")
        print(f"📁 Configuration saved to: deployment_config.json")
        
        return True
        
    except Exception as e:
        print(f"❌ Error extracting contract addresses: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 