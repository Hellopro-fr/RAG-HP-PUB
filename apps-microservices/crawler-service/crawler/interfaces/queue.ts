export interface QueueJsonContent {
    id: string;
    json: string;
    method: string;
    orderNo: number;
    retryCount: number;
    uniqueKey: string;
    url: string;
}

export interface JsonInnerContent {
    id: string;
    url: string;
    uniqueKey: string;
    method: string;
    noRetry: boolean;
    retryCount: number;
    errorMessages: string[];
    headers: Record<string, string>;
    userData: {
        __crawlee: {
            enqueueStrategy: string;
        };
    };
}

export interface UrlParameters {
    toKeep?: string[];
    toRemove?: string[];
}

