import "dotenv/config";
import { PrismaClient } from "./generated/prisma/client.js";
import { parse } from "csv-parse/sync";
import { readFileSync } from "fs";
import { resolve } from "path";

const prisma = new PrismaClient();
const RAW_DIR = resolve(import.meta.dirname, "../data/raw");

// ── helpers ──────────────────────────────────────────────────────────────────

function readCsv(filename: string): Record<string, string>[] {
  const content = readFileSync(resolve(RAW_DIR, filename), "utf-8");
  return parse(content, { columns: true, skip_empty_lines: true });
}

function toInt(v: string): number {
  return parseInt(v, 10);
}

function toFloat(v: string): number {
  return parseFloat(v);
}

function toDate(v: string): Date {
  return new Date(v);
}

function toNullableStr(v: string): string | null {
  return v === "" ? null : v;
}

function toNullableFloat(v: string): number | null {
  return v === "" ? null : parseFloat(v);
}

const BATCH_SIZE = 5000;

async function batchInsert<T>(
  label: string,
  rows: T[],
  insertFn: (batch: T[]) => Promise<unknown>,
) {
  console.log(`  ⏳ ${label}: ${rows.length} rows`);
  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);
    await insertFn(batch);
    process.stdout.write(
      `\r  ✔ ${label}: ${Math.min(i + BATCH_SIZE, rows.length)}/${rows.length}`,
    );
  }
  console.log();
}

// ── seed functions (ordered by FK dependencies) ─────────────────────────────

async function seedGeography() {
  const rows = readCsv("geography.csv");
  const data = rows.map((r) => ({
    zip: toInt(r.zip),
    city: r.city,
    region: r.region,
    district: r.district,
  }));
  await batchInsert("geography", data, (batch) =>
    prisma.geography.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedProducts() {
  const rows = readCsv("products.csv");
  const data = rows.map((r) => ({
    product_id: toInt(r.product_id),
    product_name: r.product_name,
    category: r.category,
    segment: r.segment,
    size: r.size,
    color: r.color,
    price: toFloat(r.price),
    cogs: toFloat(r.cogs),
  }));
  await batchInsert("products", data, (batch) =>
    prisma.products.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedPromotions() {
  const rows = readCsv("promotions.csv");
  const data = rows.map((r) => ({
    promo_id: r.promo_id,
    promo_name: r.promo_name,
    promo_type: r.promo_type,
    discount_value: toFloat(r.discount_value),
    start_date: toDate(r.start_date),
    end_date: toDate(r.end_date),
    applicable_category: toNullableStr(r.applicable_category),
    promo_channel: toNullableStr(r.promo_channel),
    stackable_flag: toInt(r.stackable_flag),
    min_order_value: toNullableFloat(r.min_order_value),
  }));
  await batchInsert("promotions", data, (batch) =>
    prisma.promotions.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedCustomers() {
  const rows = readCsv("customers.csv");
  const data = rows.map((r) => ({
    customer_id: toInt(r.customer_id),
    zip: toInt(r.zip),
    city: r.city,
    signup_date: toDate(r.signup_date),
    gender: toNullableStr(r.gender),
    age_group: toNullableStr(r.age_group),
    acquisition_channel: toNullableStr(r.acquisition_channel),
  }));
  await batchInsert("customers", data, (batch) =>
    prisma.customers.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedSales() {
  const rows = readCsv("sales.csv");
  const data = rows.map((r) => ({
    date: toDate(r.Date),
    revenue: toFloat(r.Revenue),
    cogs: toFloat(r.COGS),
  }));
  await batchInsert("sales", data, (batch) =>
    prisma.sales.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedWebTraffic() {
  const rows = readCsv("web_traffic.csv");
  const data = rows.map((r) => ({
    date: toDate(r.date),
    sessions: toInt(r.sessions),
    unique_visitors: toInt(r.unique_visitors),
    page_views: toInt(r.page_views),
    bounce_rate: toFloat(r.bounce_rate),
    avg_session_duration_sec: toFloat(r.avg_session_duration_sec),
    traffic_source: r.traffic_source,
  }));
  await batchInsert("web_traffic", data, (batch) =>
    prisma.web_traffic.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedOrders() {
  const rows = readCsv("orders.csv");
  const data = rows.map((r) => ({
    order_id: toInt(r.order_id),
    order_date: toDate(r.order_date),
    customer_id: toInt(r.customer_id),
    zip: toInt(r.zip),
    order_status: r.order_status,
    payment_method: r.payment_method,
    device_type: r.device_type,
    order_source: r.order_source,
  }));
  await batchInsert("orders", data, (batch) =>
    prisma.orders.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedOrderItems() {
  const rows = readCsv("order_items.csv");
  const data = rows.map((r) => ({
    order_id: toInt(r.order_id),
    product_id: toInt(r.product_id),
    quantity: toInt(r.quantity),
    unit_price: toFloat(r.unit_price),
    discount_amount: toFloat(r.discount_amount),
    promo_id: toNullableStr(r.promo_id),
    promo_id_2: toNullableStr(r.promo_id_2),
  }));
  await batchInsert("order_items", data, (batch) =>
    prisma.order_items.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedPayments() {
  const rows = readCsv("payments.csv");
  const data = rows.map((r) => ({
    order_id: toInt(r.order_id),
    payment_method: r.payment_method,
    payment_value: toFloat(r.payment_value),
    installments: toInt(r.installments),
  }));
  await batchInsert("payments", data, (batch) =>
    prisma.payments.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedShipments() {
  const rows = readCsv("shipments.csv");
  const data = rows.map((r) => ({
    order_id: toInt(r.order_id),
    ship_date: toDate(r.ship_date),
    delivery_date: toDate(r.delivery_date),
    shipping_fee: toFloat(r.shipping_fee),
  }));
  await batchInsert("shipments", data, (batch) =>
    prisma.shipments.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedReturns() {
  const rows = readCsv("returns.csv");
  const data = rows.map((r) => ({
    return_id: r.return_id,
    order_id: toInt(r.order_id),
    product_id: toInt(r.product_id),
    return_date: toDate(r.return_date),
    return_reason: r.return_reason,
    return_quantity: toInt(r.return_quantity),
    refund_amount: toFloat(r.refund_amount),
  }));
  await batchInsert("returns", data, (batch) =>
    prisma.returns.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedReviews() {
  const rows = readCsv("reviews.csv");
  const data = rows.map((r) => ({
    review_id: r.review_id,
    order_id: toInt(r.order_id),
    product_id: toInt(r.product_id),
    customer_id: toInt(r.customer_id),
    review_date: toDate(r.review_date),
    rating: toInt(r.rating),
    review_title: r.review_title,
  }));
  await batchInsert("reviews", data, (batch) =>
    prisma.reviews.createMany({ data: batch, skipDuplicates: true }),
  );
}

async function seedInventory() {
  const rows = readCsv("inventory.csv");
  const data = rows.map((r) => ({
    snapshot_date: toDate(r.snapshot_date),
    product_id: toInt(r.product_id),
    stock_on_hand: toInt(r.stock_on_hand),
    units_received: toInt(r.units_received),
    units_sold: toInt(r.units_sold),
    stockout_days: toInt(r.stockout_days),
    days_of_supply: toFloat(r.days_of_supply),
    fill_rate: toFloat(r.fill_rate),
    stockout_flag: toInt(r.stockout_flag),
    overstock_flag: toInt(r.overstock_flag),
    reorder_flag: toInt(r.reorder_flag),
    sell_through_rate: toFloat(r.sell_through_rate),
    product_name: r.product_name,
    category: r.category,
    segment: r.segment,
    year: toInt(r.year),
    month: toInt(r.month),
  }));
  await batchInsert("inventory", data, (batch) =>
    prisma.inventory.createMany({ data: batch, skipDuplicates: true }),
  );
}

// ── main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log("🌱 Seeding database...\n");

  // Master tables (no FK dependencies)
  console.log("── Master Tables ──");
  await seedGeography();
  await seedProducts();
  await seedPromotions();
  await seedCustomers();

  // Analytical & Operational (no FK to transaction tables)
  console.log("\n── Analytical & Operational Tables ──");
  await seedSales();
  await seedWebTraffic();
  await seedInventory();

  // Transaction tables (depend on master tables)
  console.log("\n── Transaction Tables ──");
  await seedOrders();
  await seedOrderItems();
  await seedPayments();
  await seedShipments();
  await seedReturns();
  await seedReviews();

  console.log("\n✅ Seeding complete!");
}

main()
  .catch((e) => {
    console.error("❌ Seed failed:", e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
