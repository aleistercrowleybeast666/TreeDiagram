# Vendored source inventory

The pinned SilverStar mathematical SDK is stored in
`src/treediagram/algorithms/sdk/` so offline wheel installations carry the same
sources as editable checkouts. `manifest.json` lists every originating path,
SHA-256, source commit and the explicit working-tree-snapshot qualification.
The snapshot retains its Apache-2.0 license. The adjacent `native/` host bridge
is TreeDiagram adapter code, not a modification of the original math kernels.
