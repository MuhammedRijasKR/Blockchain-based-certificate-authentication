import json
import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("PINATA_API_KEY")
api_secret = os.getenv("PINATA_API_SECRET")


def upload_to_pinata(file_path, user_email):
    """Uploads a file to Pinata and returns IPFS hash."""
    pinata_api_url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {
        "pinata_api_key": api_key,
        "pinata_secret_api_key": api_secret,
    }
    metadata = {
        "name": f"{os.path.basename(file_path)}",
        "keyvalues": {
            "user_email": str(user_email)
        }
    }

    with open(file_path, "rb") as file:
        files = {"file": (file.name, file), "pinataMetadata": (None, json.dumps(metadata), "application/json")}
        response = requests.post(pinata_api_url, headers=headers, files=files)
        result = response.json()

        if "IpfsHash" in result:
            return result["IpfsHash"]
        else:
            st.error("Failed to upload to Pinata.")
            return None


def get_pinata_files(user_email):
    url = "https://api.pinata.cloud/data/pinList"
    headers = {
        "pinata_api_key": api_key,
        "pinata_secret_api_key": api_secret
    }
    params = {
        "status": "pinned",
        "pageLimit": 100  # Adjust as needed
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        files = response.json().get("rows", [])
        if files:
            return [
                file for file in files
                if file.get("metadata", {}).get("keyvalues", {}).get("user_email") == str(user_email)
            ]
    else:
        st.error("Failed to fetch files from Pinata.")
        return []


def delete_pinata_file(ipfs_hash):
    url = f"https://api.pinata.cloud/pinning/unpin/{ipfs_hash}"
    headers = {
        "pinata_api_key": api_key,
        "pinata_secret_api_key": api_secret
    }
    response = requests.delete(url, headers=headers)
    return response.status_code == 200


def get_metadata_from_pinata(ipfs_hash):
    url = "https://api.pinata.cloud/data/pinList"
    headers = {
        "pinata_api_key": api_key,
        "pinata_secret_api_key": api_secret
    }
    params = {
        "hashContains": ipfs_hash
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        if data.get("count", 0) > 0:
            return data["rows"][0].get("metadata", {})
        else:
            print("No file found with that IPFS hash.")
            return None
    else:
        print("Failed to fetch metadata:", response.text)
        return None
