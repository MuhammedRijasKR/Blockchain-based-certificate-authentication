let Certification = artifacts.require("./Certification.sol");
const fs = require('fs');

module.exports = async function (deployer, network, accounts) {
  const adminSigners = accounts.slice(0, 3);
  const approvalThreshold = 2;

  await deployer.deploy(Certification, adminSigners, approvalThreshold);
  const deployedCertification = await Certification.deployed();

  // Always start with an empty object for configData
  let configData = {};

  // Update or add the contract address
  configData.Certification = deployedCertification.address;

  // Save the updated configuration back to the file
  fs.writeFileSync('./deployment_config.json', JSON.stringify(configData, null, 2));

  console.log(`Certification contract deployed at address: ${deployedCertification.address}`);
  console.log(`Admin signers: ${adminSigners.join(', ')}`);
  console.log(`Approval threshold: ${approvalThreshold} of ${adminSigners.length}`);
};
