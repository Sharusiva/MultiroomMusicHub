import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import QRCode from "qrcode";
import { formatCode } from "./views/Lobby";

export default function Invite({ open, onOpenChange, info, room }) {
  const isLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(location.hostname);
  const base = info.public_url || (isLocal ? "" : location.origin);
  const link = base && room?.code ? `${base}/?join=${room.code}` : "";
  const [qr, setQr] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open && link) QRCode.toDataURL(link, { margin: 1, width: 440, color: { dark: "#1F1E1B", light: "#F7F6F2" } }).then(setQr);
  }, [open, link]);
  useEffect(() => { if (!open) setCopied(false); }, [open]);

  const copy = () => navigator.clipboard?.writeText(link || room?.code || "").then(() => setCopied(true), () => {});

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="dialog">
          <Dialog.Title asChild><h2>Invite people to {room?.name || "this room"}</h2></Dialog.Title>
          <Dialog.Description asChild>
            <p>Only people with this code can find the room. They'll need an account, and the same Wi‑Fi as this computer.</p>
          </Dialog.Description>
          <div className="big-code num" aria-label={`Room code ${room?.code?.split("").join(" ")}`}>{formatCode(room?.code)}</div>
          {link ? (
            <>
              {qr && <img className="qr" src={qr} alt="QR code that opens the invite link" />}
              <div className="url-box num">{link}</div>
            </>
          ) : (
            <p>To invite by link or QR, start the hub with <code className="num">./start.sh</code> so it knows this computer's Wi‑Fi address. The code works either way: they open <code className="num">http://YOUR-IP</code> and choose Join with a code.</p>
          )}
          <div className="dialog-actions">
            <button className="btn solid" onClick={copy}>{copied ? "Copied" : link ? "Copy invite link" : "Copy code"}</button>
            <Dialog.Close asChild><button className="btn">Done</button></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
