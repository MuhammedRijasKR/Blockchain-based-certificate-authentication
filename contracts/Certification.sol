// SPDX-License-Identifier: MIT
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
        uint256 timestamp;
    }

    struct Institute {
        string email;
        string name;
        string public_key;
        bool is_verified;
        uint256 registered_at;
    }

    mapping(string => Certificate) public certificates;
    mapping(string => Institute) public institutes;
    mapping(string => bool) public revokedCertificates;
    string[] private certificateIds;
    string[] private instituteEmails;

    event certificateGenerated(string certificate_id, string institute_email);
    event certificateRevoked(string certificate_id);
    event instituteRegistered(string email, string name);
    event instituteVerified(string email);

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

    function verifyInstitute(string memory _email) public {
        require(bytes(institutes[_email].email).length != 0, "Institute not found");
        require(!institutes[_email].is_verified, "Institute already verified");
        
        Institute storage institute = institutes[_email];
        institute.is_verified = true;
        
        emit instituteVerified(_email);
    }

    function generateCertificate(
        string memory _certificate_id,
        string memory _uid,
        string memory _candidate_name,
        string memory _course_name,
        string memory _org_name,
        string memory _ipfs_hash,
        string memory _institute_email,
        string memory _digital_signature
    ) public {
        // Check if certificate with the given ID already exists
        require(
            bytes(certificates[_certificate_id].ipfs_hash).length == 0,
            "Certificate with this ID already exists"
        );

        // Check if institute is verified
        require(
            institutes[_institute_email].is_verified,
            "Institute must be verified to issue certificates"
        );

        // Create the certificate
        Certificate memory cert = Certificate({
            uid: _uid,
            candidate_name: _candidate_name,
            course_name: _course_name,
            org_name: _org_name,
            ipfs_hash: _ipfs_hash,
            institute_email: _institute_email,
            digital_signature: _digital_signature,
            timestamp: block.timestamp
        });

        // Store the certificate in the mapping
        certificates[_certificate_id] = cert;
        certificateIds.push(_certificate_id);

        // Emit an event
        emit certificateGenerated(_certificate_id, _institute_email);
    }

    function revokeCertificate(string memory _certificate_id) public {
        // Check if certificate exists
        require(
            bytes(certificates[_certificate_id].ipfs_hash).length != 0,
            "Certificate with this ID does not exist"
        );
        
        // Check if certificate is not already revoked
        require(
            !revokedCertificates[_certificate_id],
            "Certificate is already revoked"
        );

        // Mark certificate as revoked
        revokedCertificates[_certificate_id] = true;

        // Emit revocation event
        emit certificateRevoked(_certificate_id);
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
            uint256 _timestamp
        )
    {
        Certificate memory cert = certificates[_certificate_id];

        // Check if the certificate with the given ID exists
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
            cert.timestamp
        );
    }

    function isVerified(
        string memory _certificate_id
    ) public view returns (bool) {
        // Check if certificate exists and is not revoked
        return bytes(certificates[_certificate_id].ipfs_hash).length != 0 && 
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

    function getAllInstituteEmails() public view returns (string[] memory) {
        return instituteEmails;
    }
}
