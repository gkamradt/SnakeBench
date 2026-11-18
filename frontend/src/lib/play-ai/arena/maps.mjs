export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function shuffle(items, random) {
  for (let i = items.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [items[i], items[j]] = [items[j], items[i]];
  }
  return items;
}
// Static stones preserve connected floor and every starting head's open neighbors.
// If a dense request cannot be placed safely, record the smaller actual count.
export function placeStones(config, snakes, random) {
  const { width, height } = config,
    n = width * height,
    blocked = new Uint8Array(n),
    reserved = new Set();
  for (const s of snakes) {
    for (const [x, y] of s.body) reserved.add(y * width + x);
    const [x, y] = s.body[0];
    for (const [dx, dy] of [
      [0, -1],
      [1, 0],
      [0, 1],
      [-1, 0],
    ])
      if (x + dx >= 0 && x + dx < width && y + dy >= 0 && y + dy < height)
        reserved.add((y + dy) * width + x + dx);
  }
  // Reserve a small central patch in the terrain profile.
  for (let y = Math.floor((height - 1) / 2); y <= Math.floor(height / 2); y++)
    for (let x = Math.floor((width - 1) / 2); x <= Math.floor(width / 2); x++)
      reserved.add(y * width + x);
  const candidates = shuffle(
    Array.from({ length: n }, (_, i) => i).filter((i) => !reserved.has(i)),
    random,
  );
  const seen = new Uint32Array(n),
    queue = new Int32Array(n);
  let generation = 0;
  function connected(expected) {
    generation++;
    let start = 0;
    while (blocked[start]) start++;
    let count = 1;
    queue[0] = start;
    seen[start] = generation;
    for (let i = 0; i < count; i++) {
      const p = queue[i],
        x = p % width;
      for (const q of [
        p - width,
        x < width - 1 ? p + 1 : -1,
        p + width,
        x > 0 ? p - 1 : -1,
      ])
        if (q >= 0 && q < n && !blocked[q] && seen[q] !== generation) {
          seen[q] = generation;
          queue[count++] = q;
        }
    }
    return count === expected;
  }
  const stones = [];
  for (const p of candidates) {
    if (stones.length >= config.stones) break;
    blocked[p] = 1;
    if (connected(n - stones.length - 1))
      stones.push([p % width, Math.floor(p / width)]);
    else blocked[p] = 0;
  }
  return stones;
}
