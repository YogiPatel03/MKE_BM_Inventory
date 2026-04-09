import { useRef } from "react";
import QRCode from "react-qr-code";
import { X, Download, Printer } from "lucide-react";
import type { Bin } from "@/types";

interface BinQRModalProps {
  bin: Bin;
  onClose: () => void;
}

export function BinQRModal({ bin, onClose }: BinQRModalProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // The QR code encodes the URL that the QR scan page uses
  const qrValue = `${window.location.origin}/qr/bin/${bin.id}`;

  function getSvgElement(): SVGSVGElement | null {
    return containerRef.current?.querySelector("svg") ?? null;
  }

  function downloadSVG() {
    const svg = getSvgElement();
    if (!svg) return;
    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(svg);
    const blob = new Blob([svgStr], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bin-${bin.id}-${bin.label.replace(/\s+/g, "_")}-qr.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadPNG() {
    const svg = getSvgElement();
    if (!svg) return;
    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(svg);
    const canvas = document.createElement("canvas");
    const size = 512;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = new Image();
    const svgBlob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);
    img.onload = () => {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, size, size);
      ctx.drawImage(img, 0, 0, size, size);
      URL.revokeObjectURL(url);
      const pngUrl = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = pngUrl;
      a.download = `bin-${bin.id}-${bin.label.replace(/\s+/g, "_")}-qr.png`;
      a.click();
    };
    img.src = url;
  }

  function printQR() {
    const svg = getSvgElement();
    if (!svg) return;
    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(svg);
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>QR Code — ${bin.label}</title>
          <style>
            body { margin: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; font-family: sans-serif; }
            h2 { margin-bottom: 12px; font-size: 18px; }
            p { margin-top: 8px; font-size: 13px; color: #666; }
            @media print { button { display: none; } }
          </style>
        </head>
        <body>
          <h2>${bin.label}</h2>
          ${svgStr}
          <p>${qrValue}</p>
          <button onclick="window.print()">Print</button>
        </body>
      </html>
    `);
    win.document.close();
    win.focus();
    win.print();
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">QR Code</h2>
            <p className="text-xs text-slate-500 mt-0.5">{bin.label}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 flex flex-col items-center gap-4">
          <div ref={containerRef} className="p-3 bg-white border border-slate-200 rounded-lg">
            <QRCode
              value={qrValue}
              size={220}
              level="M"
            />
          </div>

          <p className="text-xs text-slate-400 text-center break-all">{qrValue}</p>

          <div className="flex gap-2 w-full">
            <button
              onClick={downloadPNG}
              className="btn-secondary flex-1 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              PNG
            </button>
            <button
              onClick={downloadSVG}
              className="btn-secondary flex-1 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              SVG
            </button>
            <button
              onClick={printQR}
              className="btn-primary flex-1 text-xs"
            >
              <Printer className="h-3.5 w-3.5" />
              Print
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
