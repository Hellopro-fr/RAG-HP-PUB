/**
 * @typedef {'info'|'warning'|'critical'} Severity
 *
 * @typedef {'replicas'|'capacity'|'jobs'|'capacityPlanning'} SourceName
 *
 * @typedef {Object} Sources
 * @property {Object<string, any>} replicas          WS heartbeat state
 * @property {{running_jobs, max_global_jobs, is_full}|null} capacity
 * @property {Array<{id, status, start_time, end_time}>|null} jobs
 * @property {{replicas, totals}|null} capacityPlanning
 *
 * @typedef {Object} Violation
 * @property {string=} itemKey      Undefined for global rules; set for per-item
 * @property {string} message       Human-readable message
 * @property {Object=} data         Raw context (for debugging / copy-to-clipboard)
 *
 * @typedef {Object} AutoRetryConfig
 * @property {number} maxAttempts
 * @property {number} delayMs
 * @property {Array<Array<string>>} invalidate   React Query keys
 *
 * @typedef {Object} UiHint
 * @property {string} path                        Route to navigate to
 * @property {string} label                       Human label for the link
 *
 * @typedef {Object} Rule
 * @property {string} id
 * @property {string} label
 * @property {string} description
 * @property {Severity} severity
 * @property {SourceName[]} sources
 * @property {(sources: Sources) => Violation[]} evaluate
 * @property {AutoRetryConfig=} autoRetry
 * @property {UiHint=} attachUiHint
 */

export {};
