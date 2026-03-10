import streamlit as st
from connection import contract, w3
from utils.auth import AuthManager
from utils.streamlit_utils import hide_sidebar
from utils.pinata_utils import delete_pinata_file
from utils.bloom_filter import bloom_rebuild, bloom_stats
from datetime import datetime

hide_sidebar()
auth = AuthManager()

# List of allowed admin emails - add your admin emails here
ADMIN_EMAILS = [
    "admin@blockcert.com",
    "admin@example.com",
    "admin@bc.com",
    # Add more admin emails as needed
]

auth.require_auth(allowed_roles=("admin",))

st.markdown("<h1 style='text-align: center;'>🛡️ Admin Dashboard</h1>", unsafe_allow_html=True)
st.markdown("---")

# Tabs for different admin functions
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⏳ Pending Institutes", 
    "📝 Pending Certificates",
    "📦 Pending Batches",
    "🗑️ Pending Revocations",
    "✅ Verified Institutes", 
    "📊 Statistics"
])

# --- Pending Institutes Tab ---
with tab1:
    st.markdown("### Institutes Awaiting Verification")
    
    from utils.institute_details import get_institute_details
    
    try:
        institute_emails = contract.functions.getAllInstituteEmails().call()
        
        pending_institutes = []
        for email in institute_emails:
            try:
                institute_info = contract.functions.getInstitute(email).call()
                name, public_key, is_verified, registered_at = institute_info
                if not is_verified:
                    details = get_institute_details(email)
                    pending_institutes.append({
                        "email": email,
                        "name": name,
                        "public_key": public_key,
                        "registered_at": registered_at,
                        "details": details
                    })
            except Exception:
                continue
        
        if not pending_institutes:
            st.info("🎉 No pending institutes. All institutes have been verified!")
        else:
            st.warning(f"⚠️ {len(pending_institutes)} institute(s) awaiting verification")
            
            for idx, institute in enumerate(pending_institutes):
                details = institute.get('details', {})
                with st.expander(f"📋 {institute['name']} ({institute['email']})", expanded=True):
                    
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                    with col_btn1:
                        if st.button("✅ Verify", key=f"verify_{idx}", type="primary", use_container_width=True):
                            try:
                                contract.functions.verifyInstitute(
                                    institute['email']
                                ).transact({'from': w3.eth.accounts[0]})
                                st.success(f"✅ {institute['name']} has been verified!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Verification failed: {str(e)}")
                    with col_btn2:
                        if st.button("❌ Reject", key=f"reject_{idx}", type="secondary", use_container_width=True):
                            st.warning("⚠️ Rejection feature coming soon.")
                    
                    st.markdown("---")
                    
                    st.markdown("##### 🏛️ Basic Information")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Name:** {institute['name']}")
                        st.markdown(f"**Email:** {institute['email']}")
                    with col2:
                        st.markdown(f"**Type:** {details.get('institute_type', 'N/A')}")
                        st.markdown(f"**Established:** {details.get('established_year', 'N/A')}")
                    with col3:
                        reg_date = datetime.fromtimestamp(institute['registered_at'])
                        st.markdown(f"**Registered:** {reg_date.strftime('%Y-%m-%d %H:%M')}")
                        st.markdown(f"**Accreditation:** {details.get('accreditation', 'N/A')}")
                    
                    st.markdown("##### 📞 Contact Information")
                    col4, col5 = st.columns(2)
                    with col4:
                        st.markdown(f"**Phone:** {details.get('phone_number', 'N/A')}")
                        st.markdown(f"**Website:** {details.get('website', 'N/A')}")
                    with col5:
                        st.markdown(f"**Address:** {details.get('address', 'N/A')}")
                    
                    st.markdown("##### 📄 Verification Documents")
                    st.markdown(f"**Registration/License Number:** `{details.get('registration_number', 'N/A')}`")
                    
                    st.markdown("##### 👤 Contact Person")
                    col6, col7, col8 = st.columns(3)
                    with col6:
                        st.markdown(f"**Name:** {details.get('contact_person_name', 'N/A')}")
                    with col7:
                        st.markdown(f"**Designation:** {details.get('contact_person_designation', 'N/A')}")
                    with col8:
                        st.markdown(f"**Phone:** {details.get('contact_person_phone', 'N/A')}")
                    
                    with st.expander("🔑 View Public Key"):
                        st.code(institute['public_key'], language="text")
    
    except Exception as e:
        st.error(f"❌ Error loading institutes: {str(e)}")

# --- Pending Certificates Tab ---
with tab2:
    st.markdown("### 📝 Certificates Awaiting Approval")
    st.info("Certificates proposed by institutes require admin approval before they become active.")
    
    try:
        pending_cert_ids = contract.functions.getAllPendingCertificateIds().call()
        
        if not pending_cert_ids:
            st.success("🎉 No pending certificates. All proposals have been reviewed!")
        else:
            st.warning(f"⚠️ {len(pending_cert_ids)} certificate(s) awaiting approval")
            
            for idx, cert_id in enumerate(pending_cert_ids):
                try:
                    cert_data = contract.functions.getCertificate(cert_id).call()
                    # cert_data: [0]=uid, [1]=candidate_name, [2]=course_name, [3]=org_name, 
                    #            [4]=ipfs_hash, [5]=institute_email, [6]=digital_signature, [7]=salt, [8]=grade, [9]=timestamp
                    
                    with st.expander(f"📜 Certificate: {cert_data[1]} — {cert_data[2]}", expanded=True):
                        # Action buttons
                        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                        with col_btn1:
                            if st.button("✅ Approve", key=f"approve_cert_{idx}", type="primary", use_container_width=True):
                                try:
                                    contract.functions.approveCertificate(cert_id).transact({'from': w3.eth.accounts[0]})
                                    st.success(f"✅ Certificate approved!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Approval failed: {str(e)}")
                        with col_btn2:
                            if st.button("❌ Reject", key=f"reject_cert_{idx}", type="secondary", use_container_width=True):
                                try:
                                    contract.functions.rejectCertificate(cert_id).transact({'from': w3.eth.accounts[0]})
                                    st.success("✅ Certificate rejected.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Rejection failed: {str(e)}")
                        
                        st.markdown("---")
                        
                        # Certificate details
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**UID:** {cert_data[0]}")
                            st.markdown(f"**Candidate Name:** {cert_data[1]}")
                            st.markdown(f"**Course:** {cert_data[2]}")
                            st.markdown(f"**Grade:** {cert_data[8]}")
                        with col2:
                            st.markdown(f"**Organization:** {cert_data[3]}")
                            st.markdown(f"**Institute Email:** {cert_data[5]}")
                            cert_date = datetime.fromtimestamp(cert_data[9])
                            st.markdown(f"**Proposed On:** {cert_date.strftime('%Y-%m-%d %H:%M')}")
                        
                        st.markdown(f"**Certificate ID:** `{cert_id}`")
                        
                        # Show institute info
                        try:
                            inst_info = contract.functions.getInstitute(cert_data[5]).call()
                            if inst_info[2]:  # is_verified
                                st.success(f"🏛️ Proposing Institute: **{inst_info[0]}** (Verified)")
                            else:
                                st.warning(f"🏛️ Proposing Institute: **{inst_info[0]}** (Not Verified)")
                        except:
                            pass
                
                except Exception:
                    continue
    
    except Exception as e:
        st.error(f"❌ Error loading pending certificates: {str(e)}")

# --- Pending Batches Tab ---
with tab3:
    st.markdown("### 📦 Certificate Batches Awaiting Approval")
    st.info("Institutes have proposed bulk certificate batches using Merkle trees. Review and approve.")
    
    try:
        pending_batch_ids = contract.functions.getAllPendingBatchIds().call()
        
        if not pending_batch_ids:
            st.success("🎉 No pending batches!")
        else:
            st.warning(f"⚠️ {len(pending_batch_ids)} batch(es) awaiting approval")
            
            for idx, batch_id in enumerate(pending_batch_ids):
                try:
                    batch_data = contract.functions.getBatch(batch_id).call()
                    # batch_data: [0]=merkle_root, [1]=institute_email, [2]=certificate_count, [3]=is_approved, [4]=timestamp
                    merkle_root_hex = batch_data[0].hex()
                    
                    with st.expander(f"📦 Batch #{batch_id} — {batch_data[2]} certificates", expanded=True):
                        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                        with col_btn1:
                            if st.button("✅ Approve Batch", key=f"approve_batch_{idx}", type="primary", use_container_width=True):
                                try:
                                    contract.functions.approveBatch(batch_id).transact({'from': w3.eth.accounts[0]})
                                    st.success(f"✅ Batch #{batch_id} approved!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Approval failed: {str(e)}")
                        with col_btn2:
                            if st.button("❌ Reject Batch", key=f"reject_batch_{idx}", type="secondary", use_container_width=True):
                                try:
                                    contract.functions.rejectBatch(batch_id).transact({'from': w3.eth.accounts[0]})
                                    st.success("✅ Batch rejected.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Rejection failed: {str(e)}")
                        
                        st.markdown("---")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Institute:** {batch_data[1]}")
                            st.markdown(f"**Certificate Count:** {batch_data[2]}")
                        with col2:
                            batch_date = datetime.fromtimestamp(batch_data[4])
                            st.markdown(f"**Proposed On:** {batch_date.strftime('%Y-%m-%d %H:%M')}")
                            st.markdown(f"**Batch ID:** {batch_id}")
                        
                        st.markdown(f"**Merkle Root:** `{merkle_root_hex}`")
                        
                        # Show institute info
                        try:
                            inst_info = contract.functions.getInstitute(batch_data[1]).call()
                            if inst_info[2]:
                                st.success(f"🏛️ Institute: **{inst_info[0]}** (Verified)")
                            else:
                                st.warning(f"🏛️ Institute: **{inst_info[0]}** (Not Verified)")
                        except:
                            pass

                        # CSV download for batch certificates
                        from utils.merkle_utils import _load_store
                        import csv
                        from io import StringIO
                        merkle_store = _load_store()
                        batch_store_data = merkle_store.get(str(batch_id), {})
                        batch_certs = batch_store_data.get("certificates", {})
                        if batch_certs:
                            st.markdown("---")
                            st.markdown("##### 📋 Batch Certificate Details")
                            # Build CSV
                            csv_buffer = StringIO()
                            writer = csv.writer(csv_buffer)
                            writer.writerow(["Certificate ID", "UID", "Candidate Name", "Course", "Organization", "Grade"])
                            for cert_id, cert_info in batch_certs.items():
                                writer.writerow([
                                    cert_id,
                                    cert_info.get("uid", ""),
                                    cert_info.get("candidate_name", ""),
                                    cert_info.get("course_name", ""),
                                    cert_info.get("org_name", ""),
                                    cert_info.get("grade", "")
                                ])
                            csv_data = csv_buffer.getvalue()
                            st.download_button(
                                label="📥 Download CSV",
                                data=csv_data,
                                file_name=f"batch_{batch_id}_certificates.csv",
                                mime="text/csv",
                                key=f"csv_batch_{batch_id}"
                            )
                            # Show preview table
                            import pandas as pd
                            preview_rows = []
                            for cert_id, cert_info in batch_certs.items():
                                preview_rows.append({
                                    "Name": cert_info.get("candidate_name", ""),
                                    "Course": cert_info.get("course_name", ""),
                                    "Organization": cert_info.get("org_name", ""),
                                    "Grade": cert_info.get("grade", ""),
                                    "Certificate ID": cert_id[:16] + "..."
                                })
                            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)
                
                except Exception:
                    continue
    
    except Exception as e:
        st.error(f"❌ Error loading pending batches: {str(e)}")

# --- Pending Revocations Tab ---
with tab4:
    st.markdown("### 🗑️ Revocation Requests")
    st.info("Institutes have requested these certificates to be revoked. Admin approval is required.")
    
    try:
        pending_rev_ids = contract.functions.getAllPendingRevocationIds().call()
        
        if not pending_rev_ids:
            st.success("🎉 No pending revocation requests!")
        else:
            st.warning(f"⚠️ {len(pending_rev_ids)} revocation request(s) awaiting approval")
            
            for idx, cert_id in enumerate(pending_rev_ids):
                try:
                    # Try individual certificate first
                    cert_data = None
                    batch_cert_data = None
                    is_batch_cert = False
                    try:
                        cert_data = contract.functions.getCertificate(cert_id).call()
                    except Exception:
                        pass

                    if cert_data is None or cert_data[0] == "":
                        # Fall back to batch certificate lookup
                        from utils.merkle_utils import find_certificate_batch
                        batch_id_found, batch_cert_data = find_certificate_batch(cert_id)
                        if batch_cert_data:
                            is_batch_cert = True
                        else:
                            continue  # Certificate not found anywhere

                    # Get display values
                    if is_batch_cert:
                        display_name = batch_cert_data.get("candidate_name", "Unknown")
                        display_course = batch_cert_data.get("course_name", "Unknown")
                        display_org = batch_cert_data.get("org_name", "Unknown")
                        display_uid = batch_cert_data.get("uid", "N/A")
                        display_ipfs = batch_cert_data.get("ipfs_hash", "")
                        display_email = ""
                        # Try to get institute email from batch on-chain data
                        try:
                            bd = contract.functions.getBatch(int(batch_id_found)).call()
                            display_email = bd[1]
                        except:
                            pass
                        display_date = None
                    else:
                        display_name = cert_data[1]
                        display_course = cert_data[2]
                        display_org = cert_data[3]
                        display_uid = cert_data[0]
                        display_ipfs = cert_data[4]
                        display_email = cert_data[5]
                        display_date = cert_data[9]

                    with st.expander(f"🗑️ Revoke: {display_name} — {display_course}", expanded=True):
                        if is_batch_cert:
                            st.caption(f"📦 Batch Certificate (Batch #{batch_id_found})")

                        # Action buttons
                        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                        with col_btn1:
                            if st.button("✅ Approve Revocation", key=f"approve_rev_{idx}", type="primary", use_container_width=True):
                                try:
                                    contract.functions.approveRevocation(cert_id).transact({'from': w3.eth.accounts[0]})
                                    # Also delete from IPFS
                                    if display_ipfs:
                                        delete_pinata_file(display_ipfs)
                                    st.success("✅ Certificate revoked and removed from IPFS!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Revocation approval failed: {str(e)}")
                        with col_btn2:
                            if st.button("❌ Reject Revocation", key=f"reject_rev_{idx}", type="secondary", use_container_width=True):
                                try:
                                    contract.functions.rejectRevocation(cert_id).transact({'from': w3.eth.accounts[0]})
                                    st.success("✅ Revocation request rejected. Certificate remains active.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Rejection failed: {str(e)}")
                        
                        st.markdown("---")
                        
                        # Certificate details
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**UID:** {display_uid}")
                            st.markdown(f"**Candidate Name:** {display_name}")
                            st.markdown(f"**Course:** {display_course}")
                        with col2:
                            st.markdown(f"**Organization:** {display_org}")
                            if display_email:
                                st.markdown(f"**Institute Email:** {display_email}")
                            if display_date:
                                cert_date = datetime.fromtimestamp(display_date)
                                st.markdown(f"**Issued On:** {cert_date.strftime('%Y-%m-%d %H:%M')}")
                        
                        st.markdown(f"**Certificate ID:** `{cert_id}`")
                
                except Exception:
                    continue
    
    except Exception as e:
        st.error(f"❌ Error loading revocation requests: {str(e)}")

# --- Verified Institutes Tab ---
with tab5:
    st.markdown("### Verified Institutes")
    
    try:
        institute_emails = contract.functions.getAllInstituteEmails().call()
        
        verified_institutes = []
        for email in institute_emails:
            try:
                institute_info = contract.functions.getInstitute(email).call()
                name, public_key, is_verified, registered_at = institute_info
                if is_verified:
                    verified_institutes.append({
                        "email": email,
                        "name": name,
                        "public_key": public_key,
                        "registered_at": registered_at
                    })
            except Exception:
                continue
        
        if not verified_institutes:
            st.info("No verified institutes yet.")
        else:
            st.success(f"✅ {len(verified_institutes)} verified institute(s)")
            
            for institute in verified_institutes:
                with st.expander(f"✅ {institute['name']} ({institute['email']})"):
                    st.markdown(f"**Name:** {institute['name']}")
                    st.markdown(f"**Email:** {institute['email']}")
                    
                    reg_date = datetime.fromtimestamp(institute['registered_at'])
                    st.markdown(f"**Registered:** {reg_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    with st.expander("View Public Key"):
                        st.code(institute['public_key'], language="text")
    
    except Exception as e:
        st.error(f"❌ Error loading institutes: {str(e)}")

# --- Statistics Tab ---
with tab6:
    st.markdown("### System Statistics")
    
    try:
        institute_emails = contract.functions.getAllInstituteEmails().call()
        certificate_ids = contract.functions.getAllCertificateIds().call()
        pending_cert_ids = contract.functions.getAllPendingCertificateIds().call()
        pending_rev_ids = contract.functions.getAllPendingRevocationIds().call()
        
        # Count verified vs pending institutes
        verified_count = 0
        pending_inst_count = 0
        for email in institute_emails:
            try:
                institute_info = contract.functions.getInstitute(email).call()
                if institute_info[2]:
                    verified_count += 1
                else:
                    pending_inst_count += 1
            except Exception:
                continue
        
        # Display stats
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📜 Approved Certificates", len(certificate_ids))
            st.metric("📝 Pending Certificates", len(pending_cert_ids))
        
        with col2:
            st.metric("🏛️ Total Institutes", len(institute_emails))
            st.metric("✅ Verified Institutes", verified_count)
        
        with col3:
            st.metric("⏳ Pending Institutes", pending_inst_count)
            st.metric("🗑️ Pending Revocations", len(pending_rev_ids))
        
        st.markdown("---")
        
        st.markdown("### 🔗 Smart Contract Info")
        st.code(f"Contract Address: {contract.address}", language="text")

        # --- Bloom Filter Management ---
        st.markdown("### 🌸 Bloom Filter")
        stats = bloom_stats()
        bcol1, bcol2, bcol3 = st.columns(3)
        bcol1.metric("Items", stats["items_inserted"])
        bcol2.metric("Fill Ratio", f"{stats['fill_ratio']*100:.1f}%")
        bcol3.metric("FP Rate", f"{stats['false_positive_rate']*100:.4f}%")

        if st.button("🔄 Rebuild Bloom Filter from Blockchain"):
            all_ids = list(certificate_ids) + list(pending_cert_ids)
            # Also include batch certificate IDs from local proofs
            import os, json as _json
            batch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "batch_proofs")
            if os.path.isdir(batch_dir):
                for fname in os.listdir(batch_dir):
                    if fname.endswith(".json"):
                        with open(os.path.join(batch_dir, fname)) as f:
                            bp = _json.load(f)
                        for c in bp.get("certificates", []):
                            cid = c.get("certificate_id")
                            if cid:
                                all_ids.append(cid)
            result = bloom_rebuild(all_ids)
            st.success(f"✅ Bloom Filter rebuilt with {result['items_inserted']} certificate IDs.")
            st.rerun()
        
    except Exception as e:
        st.error(f"❌ Error loading statistics: {str(e)}")
