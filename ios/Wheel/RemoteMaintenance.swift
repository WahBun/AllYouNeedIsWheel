import SwiftUI
import UIKit

/// Builds an address from the user's saved backend, never from embedded device data.
enum RemoteMaintenance {
    static func screenURL(_ address: String) -> URL? {
        guard let base = URLComponents(string: address.trimmingCharacters(in: .whitespacesAndNewlines)),
              base.scheme == "https", let host = base.host, !host.isEmpty,
              base.user == nil, base.password == nil, base.query == nil, base.fragment == nil else { return nil }
        var result = URLComponents()
        result.scheme = "vnc"
        result.host = host
        return result.url
    }
}

struct RemoteMaintenanceView: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.openURL) private var openURL
    @State private var unavailable = false
    @State private var copied = false
    private var target: URL? { RemoteMaintenance.screenURL(store.address) }

    var body: some View {
        Form {
            Section("Screen sharing") {
                if let target {
                    Text(target.host ?? "").textSelection(.enabled)
                    Button("Open screen sharing", systemImage: "desktopcomputer") {
                        openURL(target) { accepted in unavailable = !accepted }
                    }
                    Button(LocalizedStringKey(copied ? "Copied" : "Copy connection address"), systemImage: "doc.on.doc") {
                        UIPasteboard.general.string = target.absoluteString
                        copied = true
                    }
                } else {
                    Text("Save your Mini HTTPS backend address in Settings first.")
                }
                Text("On Mac, use Screen Sharing. On iPhone, a compatible VNC client is required; Wheel does not include a remote desktop client.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Reconnect Gateway") {
                Text("1. Keep Tailscale connected on both devices.")
                Text("2. Sign in to screen sharing with the Mini macOS account and password, not your IB account.")
                Text("3. In Gateway, enter your IB password and complete IB Key verification on your phone.")
                Text("4. Return to Wheel and tap Connect. Closing the remote viewer does not require quitting Gateway.")
            }
            Section("Keyboard and access") {
                Text("If typing is incorrect, select ABC on Mini and check Caps Lock. Use Mini's Accessibility Keyboard if needed. Test ordinary text before typing a password.")
                Text("Mini must allow your macOS account to observe and control the screen. Use Standard sharing; no public port forwarding is needed.")
                Text("Wheel does not store remote desktop or IB passwords.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Remote maintenance")
        .alert("No compatible screen sharing app", isPresented: $unavailable) {
            Button("OK", role: .cancel) { }
        } message: {
            Text("Copy the connection address into your VNC client, or use Screen Sharing on your Mac.")
        }
    }
}
