export const env = {
  port: parseInt(process.env.PORT || "3000", 10),
  db: {
    // host: process.env.DB_HOST || "localhost",
    host:  "localhost",
    port: parseInt(process.env.DB_PORT || "5432", 10),
    user: process.env.DB_USER || "daduhe",
    password: process.env.DB_PASSWORD || "daduhe_dev",
    database: process.env.DB_NAME || "daduhe",
  },
  docParserUrl: process.env.DOC_PARSER_URL || "http://localhost:8080",
};
