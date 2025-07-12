#!/usr/bin/env python3
"""
Quick script to add yourself as an admin
"""
import os
import re

def add_admin_email(email):
    """Add email to admin list in admin.py"""
    admin_file = "application/pages/admin/admin.py"
    
    if not os.path.exists(admin_file):
        print("❌ Admin file not found!")
        return False
    
    # Read the file
    with open(admin_file, 'r') as f:
        content = f.read()
    
    # Find the admin_emails list
    pattern = r'admin_emails = \[(.*?)\]'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("❌ Could not find admin_emails list!")
        return False
    
    current_list = match.group(1)
    
    # Check if email is already in the list
    if email in current_list:
        print(f"✅ Email {email} is already in the admin list!")
        return True
    
    # Add the email to the list
    if current_list.strip() == "":
        new_list = f'    "{email}"'
    else:
        new_list = current_list.rstrip() + f',\n    "{email}"'
    
    # Replace the list
    new_content = re.sub(pattern, f'admin_emails = [{new_list}]', content, flags=re.DOTALL)
    
    # Write back to file
    with open(admin_file, 'w') as f:
        f.write(new_content)
    
    print(f"✅ Successfully added {email} as admin!")
    print("🔄 Please restart the Streamlit application for changes to take effect.")
    return True

def main():
    print("🔧 Admin Setup Tool")
    print("==================")
    
    email = input("Enter your email address to add as admin: ").strip()
    
    if not email:
        print("❌ Email cannot be empty!")
        return
    
    if "@" not in email:
        print("❌ Please enter a valid email address!")
        return
    
    if add_admin_email(email):
        print("\n📝 Next steps:")
        print("1. Restart the Streamlit application")
        print("2. Login with your email")
        print("3. Go to the Admin page")
        print("4. You can now verify institutes!")

if __name__ == "__main__":
    main() 