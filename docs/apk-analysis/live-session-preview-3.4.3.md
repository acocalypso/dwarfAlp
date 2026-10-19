# Session image transport, app 3.4.3

Reviewed 2026-10-19 for Dwarfium session viewing. APK package
`com.convergence.dwarflab`, version 3.4.3 (750), base APK SHA-256
`98f45d1f80e51923e812c5ec431e097e9f5b63ea29f95df52a0c05f7dd4cdd4f`.
This report records protocol findings; vendor source and private captures are
excluded.

| Finding | Evidence and scope | Confidence |
|---|---|---|
| JPEG images are delivered as a persistent stream, not by repeatedly reading the newest album entry. | REA `ev_26b82f6f1831105e9c254f4d213eef44d8ee82092fbff441870283e95622a6ef`: `WifiCameraCommand.o` obtains decoded bitmaps from its stream reader. | Observed shipped code |
| Reader consumes each image's declared Content-Length and decodes its bytes. | REA `ev_24013eee529d112fe6071de158fbaee149ebafda0eec668b85b512cd2e7f26bf`: `defpackage.y44.j`. | Observed shipped code |
| Camera channel selects the telephoto or wide image destination; the app may apply display curves to the received bitmap. | REA `ev_8419808738b7c6fa6617eec19c8fb4cf834a693f5bb06b64578b829572ba1509`: `CaptureViewModel.l1.invokeSuspend`. | Observed shipped code |
| Telephoto stream is `http://<device>:8092/mainstream`; wide stream is `/secondstream`. | Historical 3.4.1 `ApiService` Retrofit declarations; current SDK URLs; bounded D3 runtime confirms telephoto response is `multipart/x-mixed-replace; boundary=boundary`. Latest app's `dsa.k/j` still dispatches to ApiService `a/c` (`ev_18d9d2e2e3e165e5ac881c81783d57b7b7b7941d79fa0a1560d6e5336a276b2a`, `ev_fa6de78b6cdaa8cb1d55e16f869e174e709d7b2ce30a32fbc8b9e9757af8c76f`). | Historical declaration plus current runtime corroboration |
| Captured and stacked counts are separate updates, not complete snapshots. | D3 runtime: `15209` capture packets omit updateType (zero) and increment currentCount; stack packets use updateType=1, stackedCount=1 and omit currentCount. UpdateType=2 begins a fresh capture sequence. | Observed runtime; reset also matches existing capture lifecycle handling |

A bounded telephoto test requested three one-second exposures without mount or
focus commands. It completed with three captured frames and one stacked frame.
The JPEG reader received three complete, different JPEGs (741095, 1293741,
1834337 bytes). This establishes changing session image delivery and stack
progress, not astronomical image quality or a one-to-one image/progress pairing.

A second browser test started five one-second exposures through Fleet and
opened Camera during the same capture. The session viewer decoded a 3856×2180
image automatically, displayed capture counts from zero through five, then
displayed one stacked frame and a subsequent 1920×1080 image. The framing
viewer was unmounted during capture. The device subsequently returned to idle;
the test released ownership and disconnected. This confirms actual browser
rendering, not merely successful HTTP headers.

Implementation implications:

- Reuse the selected device's command subscription and its physical HTTP host.
  Viewing images must not invoke Go Live, change exposure, or restart capture.
- Filter capture progress by camera; retain the unrelated counter when an
  update omits it. Clear image/counter identity on a new connection or capture.
- Cancel the upstream HTTP stream when a viewer leaves. Preserve multipart
  boundaries through proxies and avoid caching the response.
- Preserve uint64 parameter IDs as JSON text through proxies. Parsing them as
  JavaScript numbers before SDK decoding changes the requested parameter.

Unresolved boundaries: Mini and DWARF II were not exercised in this pass;
simultaneous wide/tele capture was tested in software only. Separate selectable
single-exposure and stack image channels, final FITS image fidelity, night-sky
stacking quality and DWARFLAB's display-curve equivalence are not established.
