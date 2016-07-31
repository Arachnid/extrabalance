/* Computes how much each account contributed to the DAO's extraBalance account.
 *
 * Instead of messing around with DAO internals, or calculating ratios, this code takes
 * a very simple approach:
 *
 * First, Get a list of all token creation events and the block they occurred in; group
 * by block number.
 * 
 * Then, for each block:
 *  1) Determine how much the extraBalance account increased by
 *  2) Determine how many tokens were issued
 *  3) Divide the extraBalance increase by the token count, to get an eth-per-token value.
 *  4) For each token issuance in the current block, multiply the eth-per-token value by the
 *     number of tokens issued. This is the amount this account contributed to extraBalance
 *     in this block. Increment a map from accounts to balances appropriately.
 */

var Web3 = require("web3");
web3 = new Web3(new Web3.providers.HttpProvider("http://localhost:8545"));

var abiArray = [{"constant":true,"inputs":[],"name":"extraBalance","outputs":[{"name":"","type":"address"}],"type":"function"}, {"anonymous":false,"inputs":[{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"amount","type":"uint256"}],"name":"CreatedToken","type":"event"}]
var dao = web3.eth.contract(abiArray);
var daoAddress = '0xbb9bc244d798123fde783fcc1c72d3bb8c189413';
var theDao=dao.at(daoAddress);
var extraBalanceAddress = theDao.extraBalance();

// All CreatedToken events during the DAO creation phase.
var daoLogs = theDao.CreatedToken({}, {fromBlock: 1429038, toBlock: 1599205});
daoLogs.get(function(error, results)
{
	if(error) {
		console.log("Error: " + error);
		return;
	} else {
		// tokenMap is a mapping from block number to sub-maps from account to amount.
		// eg: {1234: {"0xabcd": 42}} indicates that in block 1234, address 0xabcd received
		// 42 tokens.
		var tokenMap = {};
		for(var i = 0; i < results.length; i++) {
			var result = results[i];
			blockTokens = tokenMap[result.blockNumber];
			if(blockTokens == undefined) {
				blockTokens = {};
				tokenMap[result.blockNumber] = blockTokens;
			}
			accountTokens = blockTokens[result.args.to];
			if(blockTokens[result.args.to] == undefined) {
				blockTokens[result.args.to] = result.args.amount;
			} else {
				blockTokens[result.args.to] = blockTokens[result.args.to].plus(result.args.amount);
			}
		}

		// contributions is a map from address to total contribution to extraBalance.
		var contributions = {};
		var blockNumbers = Object.keys(tokenMap).sort();
		// totalValue tracks the sum of all contributions.
		var totalValue = web3.toBigNumber(0);
		for(var i = 0; i < blockNumbers.length; i++) {
			var blockNumber = blockNumbers[i];
			var blockMap = tokenMap[blockNumber];

			// Determine how much ETH was added to the extraBalance in this block.
			var extraBalanceDelta = web3.eth.getBalance(extraBalanceAddress, blockNumber).sub(web3.eth.getBalance(extraBalanceAddress, blockNumber - 1));
			// Determine how many tokens were issued in this block.
			var tokenDelta = Object.keys(blockMap).reduce(function(prev, curr) {
				return prev.plus(blockMap[curr])
			}, web3.toBigNumber(0))

			// Map extraBalance contributions to accounts
			for(var address in blockMap) {
				// How many extraBalance wei this address contributed			
				// value = tokens * (extraBalanceDelta / tokenDelta)
				// value = (tokens * extraBalanceDelta) / tokenDelta
				var value = blockMap[address].times(extraBalanceDelta).dividedBy(tokenDelta);
				if(value.gt(0)) {
					totalValue = totalValue.plus(value);
					if(address in contributions) {
						contributions[address] = contributions[address].plus(value);
					} else {
						contributions[address] = value;
					}
				}
			}
			console.log("Processed block " + blockNumber + " with total extraBalance " + web3.fromWei(totalValue))
		}

		console.log(JSON.stringify(contributions));
		console.log("Calculated totalValue: " + web3.fromWei(totalValue));
		console.log("extraBalance account: " + web3.eth.getBalance(extraBalanceAddress));
	}
});
