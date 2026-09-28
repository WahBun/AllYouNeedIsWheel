# Holdings image sharing

Allocation keeps its existing layout and adds a trailing share button. The sheet previews a 1080px image and opens the system share sheet only after the user taps Share image.

Seven bundled backgrounds are available, with random selection excluding the current built-in background. A PhotosPicker import adds a reusable custom slot; the last imported image is downsampled, re-encoded without original metadata, and stored in local Application Support. Imports replace that slot. No photo is uploaded by this feature.

The artwork follows AnalyticsStudio's exposure calculation: sum absolute position market values by symbol, add positive cash, normalize to total. Short positions therefore count toward exposure rather than subtracting from assets. This is deliberately distinct from Allocation's positive-assets chart. No account identifiers or monetary values are exported. A snapshot is fixed when opening the sheet; changing backgrounds does not change holdings.

Artwork uses AnalyticsStudio's existing backdrop and center image plus six generated backgrounds. Native Canvas renders the colored outer glow, separators, inner ring, and labels. Tiny slices below 2.5% retain their sector but omit labels to avoid overlap.

Validation: isolated staged checkout builds and passes 79 iOS tests, including seven background export renders, exposure aggregation, invalid-image handling and imported-image downsampling. Export preview inspected locally. Full interactive photo-picker and physical-device share-target checks remain manual. Existing uncommitted Allocation implementation and required color helpers are included as prerequisites; unrelated local edits are excluded.
