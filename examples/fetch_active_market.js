// Minimal reference: fetch a single active, open market from the Polymarket
// Gamma API and print its question plus its [Yes, No] CLOB token IDs.
//
// Run with Node 18+ (global fetch) or any runtime that exposes `fetch`.
//
//   node examples/fetch_active_market.js

const response = await fetch(
  "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=1"
);
const markets = await response.json();

const market = markets[0];
console.log(market.question);
console.log(market.clobTokenIds);
// ["123456...", "789012..."]  — [Yes token ID, No token ID]
