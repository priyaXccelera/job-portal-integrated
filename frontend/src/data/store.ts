// Single entry point for all data access. Pages import from here only.
// Every function is gated by USE_MOCK (see storeCore.ts): demo data in
// localStorage when true, real REST calls through src/api/client.ts when false.
export { USE_MOCK } from './storeCore'
export * from './storeJobs'
export * from './storeRecruiter'
export * from './storeAdmin'
