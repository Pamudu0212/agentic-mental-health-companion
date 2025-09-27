export default function CrisisCta({ href }: { href?: string | null }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center rounded-xl px-4 py-2 font-medium shadow-sm ring-1 ring-black/10"
    >
      Visit Government Mental Health Support (NIMH 1926)
    </a>
  );
}
