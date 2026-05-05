pragma solidity ^0.8.13;

contract Certification {
    struct Certificate {
        string uid;
        string candidate_name;
        string course_name;
        string org_name;
        string ipfs_hash;
        string institute_email;
        string digital_signature;
        string salt;
        string grade;
        bool is_approved;
        uint256 timestamp;
    }

    struct Institute {
        string email;
        string name;
        string public_key;
        bool is_verified;
        uint256 registered_at;
    }

    struct MerkleBatch {
        bytes32 merkle_root;
        string institute_email;
        uint256 certificate_count;
        bool is_approved;
        uint256 timestamp;
    }

    mapping(string => Certificate) public certificates;
    mapping(string => Institute) public institutes;
    mapping(string => bool) public revokedCertificates;
    mapping(string => bool) public pendingRevocations;
    mapping(uint256 => MerkleBatch) public batches;
    uint256 public batchCount;
    string[] private certificateIds;
    string[] private pendingCertificateIds;
    string[] private pendingRevocationIds;
    uint256[] private pendingBatchIds;
    string[] private instituteEmails;

    address[] private adminSigners;
    mapping(address => bool) public isAdminSigner;
    uint256 public approvalThreshold;
    mapping(string => mapping(address => bool)) private certificateApprovals;
    mapping(string => uint256) public certificateApprovalCounts;
    mapping(uint256 => mapping(address => bool)) private batchApprovals;
    mapping(uint256 => uint256) public batchApprovalCounts;

    event certificateGenerated(string certificate_id, string institute_email);
    event certificateApproved(string certificate_id);
    event certificateApprovalRecorded(string certificate_id, address admin, uint256 approval_count, uint256 required_count);
    event certificateProposed(string certificate_id, string institute_email);
    event certificateRevoked(string certificate_id);
    event revocationProposed(string certificate_id, string institute_email);
    event revocationApproved(string certificate_id);
    event batchProposed(uint256 batch_id, string institute_email, uint256 certificate_count);
    event batchApproved(uint256 batch_id);
    event batchApprovalRecorded(uint256 batch_id, address admin, uint256 approval_count, uint256 required_count);
    event instituteRegistered(string email, string name);
    event instituteVerified(string email);

    modifier onlyAdminSigner() {
        require(isAdminSigner[msg.sender], "Caller is not an admin signer");
        _;
    }

    constructor(address[] memory _adminSigners, uint256 _approvalThreshold) {
        require(_adminSigners.length > 0, "At least one admin signer required");
        require(_approvalThreshold > 0, "Approval threshold must be greater than zero");
        require(_approvalThreshold <= _adminSigners.length, "Threshold cannot exceed signer count");

        approvalThreshold = _approvalThreshold;

        for (uint256 i = 0; i < _adminSigners.length; i++) {
            address signer = _adminSigners[i];
            require(signer != address(0), "Admin signer cannot be zero address");
            require(!isAdminSigner[signer], "Duplicate admin signer");
            isAdminSigner[signer] = true;
            adminSigners.push(signer);
        }
    }

    function registerInstitute(
        string memory _email,
        string memory _name,
        string memory _public_key
    ) public {
        require(bytes(institutes[_email].email).length == 0, "Institute already registered");
        
        Institute memory newInstitute = Institute({
            email: _email,
            name: _name,
            public_key: _public_key,
            is_verified: false,
            registered_at: block.timestamp
        });
        
        institutes[_email] = newInstitute;
        instituteEmails.push(_email);
        
        emit instituteRegistered(_email, _name);
    }

    function verifyInstitute(string memory _email) public onlyAdminSigner {
        require(bytes(institutes[_email].email).length != 0, "Institute not found");
        require(!institutes[_email].is_verified, "Institute already verified");
        
        Institute storage institute = institutes[_email];
        institute.is_verified = true;
        
        emit instituteVerified(_email);
    }

    // Institute proposes a certificate (pending admin approval)
    function proposeCertificate(
        string memory _certificate_id,
        string memory _uid,
        string memory _candidate_name,
        string memory _course_name,
        string memory _org_name,
        string memory _ipfs_hash,
        string memory _institute_email,
        string memory _digital_signature,
        string memory _salt,
        string memory _grade
    ) public {
        require(
            bytes(certificates[_certificate_id].ipfs_hash).length == 0,
            "Certificate with this ID already exists"
        );

        require(
            institutes[_institute_email].is_verified,
            "Institute must be verified to issue certificates"
        );

        // Create the certificate in pending state
        Certificate memory cert = Certificate({
            uid: _uid,
            candidate_name: _candidate_name,
            course_name: _course_name,
            org_name: _org_name,
            ipfs_hash: _ipfs_hash,
            institute_email: _institute_email,
            digital_signature: _digital_signature,
            salt: _salt,
            grade: _grade,
            is_approved: false,
            timestamp: block.timestamp
        });

        certificates[_certificate_id] = cert;
        pendingCertificateIds.push(_certificate_id);

        emit certificateProposed(_certificate_id, _institute_email);
    }

    // Admin records one approval for a pending certificate. The certificate is
    // finalized only after approvalThreshold distinct admin signers approve it.
    function approveCertificate(string memory _certificate_id) public onlyAdminSigner {
        require(
            bytes(certificates[_certificate_id].ipfs_hash).length != 0,
            "Certificate does not exist"
        );
        require(
            !certificates[_certificate_id].is_approved,
            "Certificate is already approved"
        );
        require(
            !certificateApprovals[_certificate_id][msg.sender],
            "Admin already approved this certificate"
        );

        certificateApprovals[_certificate_id][msg.sender] = true;
        certificateApprovalCounts[_certificate_id] += 1;

        emit certificateApprovalRecorded(
            _certificate_id,
            msg.sender,
            certificateApprovalCounts[_certificate_id],
            approvalThreshold
        );

        if (certificateApprovalCounts[_certificate_id] < approvalThreshold) {
            return;
        }

        certificates[_certificate_id].is_approved = true;
        certificateIds.push(_certificate_id);
        _removePendingCertificate(_certificate_id);

        emit certificateApproved(_certificate_id);
        emit certificateGenerated(_certificate_id, certificates[_certificate_id].institute_email);
    }

    // Admin rejects a pending certificate
    function rejectCertificate(string memory _certificate_id) public onlyAdminSigner {
        require(
            bytes(certificates[_certificate_id].ipfs_hash).length != 0,
            "Certificate does not exist"
        );
        require(
            !certificates[_certificate_id].is_approved,
            "Cannot reject an approved certificate"
        );

        // Remove from pending list
        _removePendingCertificate(_certificate_id);

        // Delete the certificate data
        delete certificates[_certificate_id];
    }

    // Institute proposes revocation (pending admin approval)
    function proposeRevocation(string memory _certificate_id) public {
        require(
            bytes(certificates[_certificate_id].ipfs_hash).length != 0,
            "Certificate does not exist"
        );
        require(
            certificates[_certificate_id].is_approved,
            "Certificate is not yet approved"
        );
        require(
            !revokedCertificates[_certificate_id],
            "Certificate is already revoked"
        );
        require(
            !pendingRevocations[_certificate_id],
            "Revocation already pending"
        );

        pendingRevocations[_certificate_id] = true;
        pendingRevocationIds.push(_certificate_id);

        emit revocationProposed(_certificate_id, certificates[_certificate_id].institute_email);
    }

    // Institute proposes revocation for a batch certificate (not stored individually on-chain)
    function proposeRevocationBatchCert(
        string memory _certificate_id,
        string memory _institute_email
    ) public {
        require(
            !revokedCertificates[_certificate_id],
            "Certificate is already revoked"
        );
        require(
            !pendingRevocations[_certificate_id],
            "Revocation already pending"
        );

        pendingRevocations[_certificate_id] = true;
        pendingRevocationIds.push(_certificate_id);

        emit revocationProposed(_certificate_id, _institute_email);
    }

    // Admin approves revocation
    function approveRevocation(string memory _certificate_id) public onlyAdminSigner {
        require(
            pendingRevocations[_certificate_id],
            "No pending revocation for this certificate"
        );

        revokedCertificates[_certificate_id] = true;
        pendingRevocations[_certificate_id] = false;

        // Remove from pending revocation list
        _removePendingRevocation(_certificate_id);

        emit revocationApproved(_certificate_id);
        emit certificateRevoked(_certificate_id);
    }

    // Admin rejects revocation request
    function rejectRevocation(string memory _certificate_id) public onlyAdminSigner {
        require(
            pendingRevocations[_certificate_id],
            "No pending revocation for this certificate"
        );

        pendingRevocations[_certificate_id] = false;
        _removePendingRevocation(_certificate_id);
    }

    function getCertificate(
        string memory _certificate_id
    )
        public
        view
        returns (
            string memory _uid,
            string memory _candidate_name,
            string memory _course_name,
            string memory _org_name,
            string memory _ipfs_hash,
            string memory _institute_email,
            string memory _digital_signature,
            string memory _salt,
            string memory _grade,
            uint256 _timestamp
        )
    {
        Certificate memory cert = certificates[_certificate_id];

        require(
            bytes(cert.ipfs_hash).length != 0,
            "Certificate with this ID does not exist"
        );

        return (
            cert.uid,
            cert.candidate_name,
            cert.course_name,
            cert.org_name,
            cert.ipfs_hash,
            cert.institute_email,
            cert.digital_signature,
            cert.salt,
            cert.grade,
            cert.timestamp
        );
    }

    function isCertificateApproved(
        string memory _certificate_id
    ) public view returns (bool) {
        return certificates[_certificate_id].is_approved;
    }

    function isPendingRevocation(
        string memory _certificate_id
    ) public view returns (bool) {
        return pendingRevocations[_certificate_id];
    }

    function isVerified(
        string memory _certificate_id
    ) public view returns (bool) {
        return bytes(certificates[_certificate_id].ipfs_hash).length != 0 && 
               certificates[_certificate_id].is_approved &&
               !revokedCertificates[_certificate_id];
    }

    function isRevoked(
        string memory _certificate_id
    ) public view returns (bool) {
        return revokedCertificates[_certificate_id];
    }

    function getInstitute(
        string memory _email
    ) public view returns (
        string memory _name,
        string memory _public_key,
        bool _is_verified,
        uint256 _registered_at
    ) {
        Institute memory institute = institutes[_email];
        require(bytes(institute.email).length != 0, "Institute not found");
        
        return (
            institute.name,
            institute.public_key,
            institute.is_verified,
            institute.registered_at
        );
    }

    function isInstituteVerified(string memory _email) public view returns (bool) {
        return institutes[_email].is_verified;
    }

    function getAllCertificateIds() public view returns (string[] memory) {
        return certificateIds;
    }

    function getAllPendingCertificateIds() public view returns (string[] memory) {
        return pendingCertificateIds;
    }

    function getAllPendingRevocationIds() public view returns (string[] memory) {
        return pendingRevocationIds;
    }

    function getAllInstituteEmails() public view returns (string[] memory) {
        return instituteEmails;
    }

    function getAdminSigners() public view returns (address[] memory) {
        return adminSigners;
    }

    function getCertificateApprovalStatus(
        string memory _certificate_id,
        address _admin
    ) public view returns (uint256 _approval_count, uint256 _required_count, bool _approved_by_admin) {
        return (
            certificateApprovalCounts[_certificate_id],
            approvalThreshold,
            certificateApprovals[_certificate_id][_admin]
        );
    }

    // ===== Merkle Batch Functions =====

    // Institute proposes a batch of certificates
    function proposeBatch(
        bytes32 _merkle_root,
        string memory _institute_email,
        uint256 _certificate_count
    ) public {
        require(
            institutes[_institute_email].is_verified,
            "Institute must be verified"
        );

        batchCount++;
        batches[batchCount] = MerkleBatch({
            merkle_root: _merkle_root,
            institute_email: _institute_email,
            certificate_count: _certificate_count,
            is_approved: false,
            timestamp: block.timestamp
        });

        pendingBatchIds.push(batchCount);
        emit batchProposed(batchCount, _institute_email, _certificate_count);
    }

    // Admin records one approval for a batch. The batch is finalized only after
    // approvalThreshold distinct admin signers approve it.
    function approveBatch(uint256 _batch_id) public onlyAdminSigner {
        require(_batch_id > 0 && _batch_id <= batchCount, "Invalid batch ID");
        require(!batches[_batch_id].is_approved, "Batch already approved");
        require(!batchApprovals[_batch_id][msg.sender], "Admin already approved this batch");

        batchApprovals[_batch_id][msg.sender] = true;
        batchApprovalCounts[_batch_id] += 1;

        emit batchApprovalRecorded(
            _batch_id,
            msg.sender,
            batchApprovalCounts[_batch_id],
            approvalThreshold
        );

        if (batchApprovalCounts[_batch_id] < approvalThreshold) {
            return;
        }

        batches[_batch_id].is_approved = true;
        _removePendingBatch(_batch_id);

        emit batchApproved(_batch_id);
    }

    // Admin rejects a batch
    function rejectBatch(uint256 _batch_id) public onlyAdminSigner {
        require(_batch_id > 0 && _batch_id <= batchCount, "Invalid batch ID");
        require(!batches[_batch_id].is_approved, "Cannot reject approved batch");

        _removePendingBatch(_batch_id);
        delete batches[_batch_id];
    }

    // Get batch details
    function getBatch(uint256 _batch_id) public view returns (
        bytes32 _merkle_root,
        string memory _institute_email,
        uint256 _certificate_count,
        bool _is_approved,
        uint256 _timestamp
    ) {
        require(_batch_id > 0 && _batch_id <= batchCount, "Invalid batch ID");
        MerkleBatch memory batch = batches[_batch_id];
        return (
            batch.merkle_root,
            batch.institute_email,
            batch.certificate_count,
            batch.is_approved,
            batch.timestamp
        );
    }

    function getAllPendingBatchIds() public view returns (uint256[] memory) {
        return pendingBatchIds;
    }

    function getBatchCount() public view returns (uint256) {
        return batchCount;
    }

    function getBatchApprovalStatus(
        uint256 _batch_id,
        address _admin
    ) public view returns (uint256 _approval_count, uint256 _required_count, bool _approved_by_admin) {
        return (
            batchApprovalCounts[_batch_id],
            approvalThreshold,
            batchApprovals[_batch_id][_admin]
        );
    }

    // ===== Internal Helpers =====

    function _removePendingCertificate(string memory _certificate_id) internal {
        for (uint i = 0; i < pendingCertificateIds.length; i++) {
            if (keccak256(bytes(pendingCertificateIds[i])) == keccak256(bytes(_certificate_id))) {
                pendingCertificateIds[i] = pendingCertificateIds[pendingCertificateIds.length - 1];
                pendingCertificateIds.pop();
                break;
            }
        }
    }

    function _removePendingRevocation(string memory _certificate_id) internal {
        for (uint i = 0; i < pendingRevocationIds.length; i++) {
            if (keccak256(bytes(pendingRevocationIds[i])) == keccak256(bytes(_certificate_id))) {
                pendingRevocationIds[i] = pendingRevocationIds[pendingRevocationIds.length - 1];
                pendingRevocationIds.pop();
                break;
            }
        }
    }

    function _removePendingBatch(uint256 _batch_id) internal {
        for (uint i = 0; i < pendingBatchIds.length; i++) {
            if (pendingBatchIds[i] == _batch_id) {
                pendingBatchIds[i] = pendingBatchIds[pendingBatchIds.length - 1];
                pendingBatchIds.pop();
                break;
            }
        }
    }
}
