from ethereum import utils, abi, transactions, tester, state_transition
import json
import rlp


trustee_address = '0xda4a4626d3e16e094de3225a751aab7128e96526'


# Compiled with Solidity v0.3.5-2016-07-21-6610add with optimization enabled.
"""
contract MultiSend {
    function MultiSend(address[] recipients, uint[] amounts, address remainder) {
        if(recipients.length != amounts.length)
            throw;
        
        for(uint i = 0; i < recipients.length; i++) {
            recipients[i].send(amounts[i]);
        }
        
        selfdestruct(remainder);
    }
}
"""
multisend_contract = "60606040526040516099380380609983398101604052805160805160a05191830192019081518351600091146032576002565b5b8351811015608d578381815181101560025790602001906020020151600160a060020a031660008483815181101560025790602001906020020151604051809050600060405180830381858888f150505050506001016033565b81600160a060020a0316ff".decode('hex')
multisend_abi = [{"inputs":[{"name":"recipients","type":"address[]"},{"name":"amounts","type":"uint256[]"},{"name":"remainder","type":"address"}],"type":"constructor"},{"anonymous":False,"inputs":[{"indexed":True,"name":"recipient","type":"address"},{"indexed":False,"name":"amount","type":"uint256"}],"name":"SendFailure","type":"event"}]


def make_trustless_multisend(payouts, remainder, gasprice=20 * 10**9):
    """
    Creates a transaction that trustlessly sends money to multiple recipients, and any
    left over (unsendable) funds to the address specified in remainder.

    Arguments:
      payouts: A list of (address, value tuples)
      remainder: An address in hex form to send any unsendable balance to
      gasprice: The gas price, in wei
    Returns: A transaction object that accomplishes the multisend.
    """
    ct = abi.ContractTranslator(multisend_abi)
    addresses = [utils.normalize_address(addr) for addr, value in payouts]
    values = [value for addr, value in payouts]
    cdata = ct.encode_constructor_arguments([addresses, values, utils.normalize_address(remainder)])
    tx = transactions.Transaction(
        0,
        gasprice,
        50000 + len(addresses) * 35000,
        '',
        sum(values),
        multisend_contract + cdata)
    tx.v = 27
    tx.r = 0x0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0
    tx.s = 0x0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0
    while True:
        try:
            tx.sender
            return tx
        except Exception, e:
            # Failed to generate public key
            tx.r += 1


def test_multisends(payouts, transactions):
    s = tester.state()
    roottx = transactions[0]
    s.state.set_balance(roottx.sender, roottx.value + roottx.startgas * roottx.gasprice)
    gas_used = 0
    for i, tx in enumerate(transactions):
        s.state.get_balance(roottx.sender)
        state_transition.apply_transaction(s.state, tx)
        print "Applying transaction number %d consumed %d gas out of %d" % (i, s.state.gas_used - gas_used, tx.startgas)
        gas_used = s.state.gas_used

    for addr, value in payouts:
        balance = s.state.get_balance(utils.normalize_address(addr))
        assert balance == value, (addr, balance, value)
    return s.state.gas_used


def build_recursive_multisend(payouts, remainder, batchsize):
    """Builds a recursive set of multisend transactions.

    Arguments:
      payouts: A map from address to value to send.
      remainder: An address to send any unsent funds back to.
      batchsize: Maximum payouts per transaction.
    Returns:
      (rootaddr, value, transactions)
    """
    transactions = []

    for i in range(0, len(payouts), batchsize):
        txpayouts = payouts[i:i + batchsize]
        tx = make_trustless_multisend(txpayouts, remainder)
        transactions.append(tx)

    if len(transactions) == 1:
        tx = transactions[0]
        return (tx.sender, tx.value + tx.startgas * tx.gasprice, transactions)
    else:
        subpayouts = [(tx.sender, tx.value + tx.startgas * tx.gasprice) for tx in transactions]
        rootaddr, value, subtx = build_recursive_multisend(subpayouts, remainder, batchsize)
        return (rootaddr, value, subtx + transactions)


if __name__ == '__main__':
    payouts = [(k, long(v)) for k, v in json.load(open('extrabalance.json', 'r'))]
    rootaddr, value, transactions = build_recursive_multisend(payouts, trustee_address, 110)
    test_multisends(payouts, transactions)
    print "Root address 0x%s requires %d wei funding" % (rootaddr.encode('hex'), value)
    out = open('transactions.js', 'w')
    for tx in transactions:
        out.write('web3.eth.sendRawTransaction("0x%s");\n' % (rlp.encode(tx).encode('hex'),))
    out.close()
    print "Transactions written out to transactions.js"
