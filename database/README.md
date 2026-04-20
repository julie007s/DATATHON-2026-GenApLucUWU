# Database Setup

PostgreSQL database for the Datathon 2026 dataset, managed with Prisma ORM.

## Prerequisites

- **Node.js** >= 18
- **PostgreSQL** running (local or remote)

## Quick Start

### 1. Install dependencies

```bash
cd database
npm install
```

### 2. Configure database connection

Edit `.env` and set your PostgreSQL connection string:

```env
DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
```

Example for local PostgreSQL:

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/datathon"
```

### 3. Push schema to database

This creates all tables in the database based on the Prisma schema:

```bash
npm run db:push
```

### 4. Generate Prisma client

```bash
npm run db:generate
```

### 5. Seed the database

Upload all CSV data from `data/raw/` into the database:

```bash
npm run db:seed
```

This inserts all 13 tables in the correct order (respecting FK constraints):

| Order | Table | Rows source |
|-------|-------|-------------|
| 1 | geography | geography.csv |
| 2 | products | products.csv |
| 3 | promotions | promotions.csv |
| 4 | customers | customers.csv |
| 5 | sales | sales.csv |
| 6 | web_traffic | web_traffic.csv |
| 7 | inventory | inventory.csv |
| 8 | orders | orders.csv |
| 9 | order_items | order_items.csv |
| 10 | payments | payments.csv |
| 11 | shipments | shipments.csv |
| 12 | returns | returns.csv |
| 13 | reviews | reviews.csv |

### 6. Browse data (optional)

```bash
npm run db:studio
```

Opens Prisma Studio at http://localhost:5555 for visual data browsing.

## All-in-one command

```bash
cd database
npm install
npm run db:push
npm run db:generate
npm run db:seed
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run db:generate` | Generate Prisma client |
| `npm run db:push` | Push schema to database (no migration history) |
| `npm run db:migrate` | Create and apply migrations |
| `npm run db:seed` | Seed all CSV data into the database |
| `npm run db:studio` | Open Prisma Studio GUI |
| `npm run db:reset` | Reset database and re-apply migrations |

## Project Structure

```
database/
├── .env                  # Database connection string
├── package.json
├── prisma.config.ts      # Prisma config
├── seed.ts               # CSV → database seed script
├── prisma/
│   └── schema.prisma     # Database schema (13 tables)
└── generated/
    └── prisma/           # Generated Prisma client (gitignored)
```
