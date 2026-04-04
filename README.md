# CSC583-Query-Optimization-by-Sharding-and-Parallelization
An experiment to benchmark the performance of a basic Boolean query engine for text retrieval using parallel query execution and sharded indexing

## Workflow: 
There are 3 types of branches for this repo:
- `master`: The main branch. No code should be directly pushed to the master branch. This should always hold the latest version of working code. The code to the master branch will be merged by creating a PR, strictly after completing a phase.
- `phase-?`: The phase branch. This branch will contain all the code required for a particular phase of the project's implementation. Code should not be pushed directly to the `phase-?` branch. For example, the phase-1 branch will only contain phase-1-related implementation code. Once the phase is complete, it will be merged with the `master` branch. To merge code to `phase-?` branch, raise a PR.
- `phase-?-dev`: This is the main dev branch for a specific phase. All code should be pushed here. Once pushed, it is contingent on review by peers, and from here, it will be merged to the `phase-?` branch by raising a PR.

#### The workflow: 
Push all code to the dev branch for that phase. Once done, raise a PR for merging to the phase-branch. Once reviewed, the PR will be approved for merge. 
Once the phase is completed and verified by all team members, it will be merged into the `master` branch.
