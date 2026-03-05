"""
Institute Details Storage Utility

Stores additional institute verification details in a JSON file.
The blockchain stores verification status, while this file stores
supporting documentation details for admin review.
"""

import json
import os
from datetime import datetime

INSTITUTE_DETAILS_FILE = "db/institute_details.json"


def _ensure_file_exists():
    """Ensure the institute details file exists"""
    os.makedirs(os.path.dirname(INSTITUTE_DETAILS_FILE), exist_ok=True)
    if not os.path.exists(INSTITUTE_DETAILS_FILE):
        with open(INSTITUTE_DETAILS_FILE, 'w') as f:
            json.dump({}, f)


def save_institute_details(email: str, details: dict) -> bool:
    """
    Save institute verification details
    
    Args:
        email: Institute email (unique identifier)
        details: Dictionary with institute details
    
    Returns:
        True if saved successfully
    """
    try:
        _ensure_file_exists()
        
        with open(INSTITUTE_DETAILS_FILE, 'r') as f:
            all_details = json.load(f)
        
        # Add timestamp
        details['submitted_at'] = datetime.now().isoformat()
        all_details[email] = details
        
        with open(INSTITUTE_DETAILS_FILE, 'w') as f:
            json.dump(all_details, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Error saving institute details: {e}")
        return False


def get_institute_details(email: str) -> dict:
    """
    Get institute verification details
    
    Args:
        email: Institute email
    
    Returns:
        Dictionary with institute details or empty dict if not found
    """
    try:
        _ensure_file_exists()
        
        with open(INSTITUTE_DETAILS_FILE, 'r') as f:
            all_details = json.load(f)
        
        return all_details.get(email, {})
    except Exception as e:
        print(f"Error loading institute details: {e}")
        return {}


def get_all_institute_details() -> dict:
    """
    Get all institute verification details
    
    Returns:
        Dictionary with all institute details
    """
    try:
        _ensure_file_exists()
        
        with open(INSTITUTE_DETAILS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading institute details: {e}")
        return {}


def update_institute_details(email: str, updates: dict) -> bool:
    """
    Update specific fields in institute details
    
    Args:
        email: Institute email
        updates: Dictionary with fields to update
    
    Returns:
        True if updated successfully
    """
    try:
        details = get_institute_details(email)
        details.update(updates)
        return save_institute_details(email, details)
    except Exception as e:
        print(f"Error updating institute details: {e}")
        return False
