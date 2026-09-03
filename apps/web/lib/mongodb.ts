import { MongoClient } from "mongodb";

// Singleton Mongo client for NextAuth's CredentialsProvider (bcrypt lookup
// against the `users` collection FastAPI also reads/writes — see
// apps/api/dependencies.py::get_current_user). Cached on `global` in dev so
// Next.js's hot-reload doesn't open a new connection per edit.

const uri = process.env.MONGODB_URI || "mongodb://localhost:27017";
const dbName = process.env.MONGODB_DB_NAME || "cloudcare";

declare global {
  // eslint-disable-next-line no-var
  var _mongoClientPromise: Promise<MongoClient> | undefined;
}

function getClientPromise(): Promise<MongoClient> {
  if (process.env.NODE_ENV === "development") {
    if (!global._mongoClientPromise) {
      global._mongoClientPromise = new MongoClient(uri).connect();
    }
    return global._mongoClientPromise;
  }
  return new MongoClient(uri).connect();
}

export async function getUsersCollection() {
  const client = await getClientPromise();
  return client.db(dbName).collection("users");
}
