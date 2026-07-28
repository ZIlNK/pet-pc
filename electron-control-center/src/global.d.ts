export {};

declare global {
  interface Window {
    controlCenter: {
      apiBase: string;
      choosePetImage(): Promise<{ name: string; bytes: Uint8Array } | null>;
      choosePetArchive(): Promise<{ name: string; bytes: Uint8Array } | null>;
    };
  }
}
