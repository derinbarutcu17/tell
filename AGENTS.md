# Project instructions

Read /Users/derin/Desktop/CODING/AGENTS.md, PRODUCT.md, and ARCHITECTURE.md before editing.

Keep this version small, local-first, and explicit about data leaving the device. Only inspect source folders that the user added. Never scan the whole machine, read credentials, or publish content. A model call may use only the packet created from selected sources after the user passes the explicit remote flag.

Use opencode-go/beam-free for product model calls unless the user changes the cost constraint. Do not silently switch to another provider or paid model.

Keep agent write scopes disjoint. Run the smallest relevant tests after a change. Do not commit, push, publish, or deploy.
