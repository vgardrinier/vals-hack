# Operations note BR-12 — continuity reviews

The beneficiary screen stores two links independently: `P` for the party named
on the instruction and `A` for the owner of the receiving account. Reusing an
account number can carry forward `A` only while `P` is unchanged. A corporate
relationship, trading-name comment, or relationship-manager expectation updates
neither link by itself.

When `P` changes and the file has no financial-institution or account-title
evidence, analysts leave the item in state `OV-2`. That state preserves the
requested value date but does not expose funds to settlement. The release queue
accepts `OV-0` and `OV-1`; it ignores the `commercially expected` flag used by
Treasury for cutoff planning.
