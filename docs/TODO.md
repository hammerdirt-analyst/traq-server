# Server TODO

- Add a tree-repair/admin command for customer-scoped tree conflicts.
  - Need an explicit repair flow for cases like `J0001` and `J0002` ending up on the same `tree_number` under the same customer.
  - Desired capability:
    - audit duplicate tree numbers within a customer
    - repair a job's tree assignment explicitly, e.g. allocate next available tree number or assign a requested one
  - This should be a versioned server improvement, not an ad hoc manual cleanup step.
