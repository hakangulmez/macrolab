// Intersection of the pinned Vite, Vitest and ESLint ranges; no network here.
const [major, minor] = process.versions.node.split('.').map(Number);
if (!((major === 22 && minor >= 13) || major === 24 || major >= 26)) {
  console.error(`Unsupported Node ${process.versions.node}. Ask Hakan before changing Node.`);
  process.exit(1);
}
console.log(JSON.stringify({ node: process.versions.node, status: 'available' }));
