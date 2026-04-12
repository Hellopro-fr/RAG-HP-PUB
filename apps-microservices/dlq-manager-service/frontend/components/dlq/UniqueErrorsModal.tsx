"use client"

import * as React from "react";
import { useState, useMemo } from "react"
import { X, Download, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { UniqueErrorBucket } from "@/lib/api"
import Pagination from "./Pagination"

interface UniqueErrorsModalProps {
  buckets: UniqueErrorBucket[];
  totalUnique: number;
  loading: boolean;
  onClose: () => void;
  onSelectError?: (serviceName: string, errorReason: string) => void;
}

const PAGE_SIZE = 50;

export default function UniqueErrorsModal({ buckets, totalUnique, loading, onClose, onSelectError }: UniqueErrorsModalProps) {
  const [currentPage, setCurrentPage] = useState(1);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const paginatedBuckets = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return buckets.slice(start, start + PAGE_SIZE);
  }, [buckets, currentPage]);

  const exportData = (format: 'csv' | 'json') => {
    let content: string;
    let mimeType: string;
    let filename: string;

    if (format === 'csv') {
      const header = 'service_name,error_reason,count';
      const rows = buckets.map(b =>
        `"${b.service_name.replace(/"/g, '""')}","${b.error_reason.replace(/"/g, '""')}",${b.count}`
      );
      content = [header, ...rows].join('\n');
      mimeType = 'text/csv;charset=utf-8;';
      filename = 'unique_errors.csv';
    } else {
      content = JSON.stringify(buckets, null, 2);
      mimeType = 'application/json;charset=utf-8;';
      filename = 'unique_errors.json';
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white-primary rounded-lg shadow-xl w-full max-w-4xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 md:p-6 border-b border-gris-blanc">
          <div>
            <h2 className="text-lg font-semibold text-noir-primary">Unique Errors</h2>
            <p className="text-sm text-gris-primary mt-1">
              {loading ? "Loading..." : `${totalUnique} unique service + error combinations`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => exportData('csv')}
              disabled={loading || buckets.length === 0}
              className="hidden sm:flex"
            >
              <Download className="w-4 h-4 mr-1" />
              CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => exportData('json')}
              disabled={loading || buckets.length === 0}
              className="hidden sm:flex"
            >
              <Download className="w-4 h-4 mr-1" />
              JSON
            </Button>
            <button onClick={onClose} className="text-gris-primary hover:text-noir-primary transition-colors ml-2" aria-label="Close modal">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Mobile export buttons */}
        <div className="flex sm:hidden gap-2 px-4 pt-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportData('csv')}
            disabled={loading || buckets.length === 0}
            className="flex-1"
          >
            <Download className="w-4 h-4 mr-1" />
            CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportData('json')}
            disabled={loading || buckets.length === 0}
            className="flex-1"
          >
            <Download className="w-4 h-4 mr-1" />
            JSON
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 md:p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-bleu-primary mr-2" />
              <span className="text-gris-primary">Loading unique errors...</span>
            </div>
          ) : buckets.length === 0 ? (
            <div className="text-center py-12 text-gris-primary">
              No unique error combinations found for the current filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gris-blanc">
                    <th className="text-left p-3 font-medium text-gris-primary">#</th>
                    <th className="text-left p-3 font-medium text-gris-primary">Service Name</th>
                    <th className="text-left p-3 font-medium text-gris-primary">Error Reason</th>
                    <th className="text-right p-3 font-medium text-gris-primary">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedBuckets.map((bucket, index) => (
                    <tr
                      key={`${bucket.service_name}-${bucket.error_reason}`}
                      className={`border-b border-gris-blanc transition-colors ${onSelectError ? 'hover:bg-bleu-light cursor-pointer' : 'hover:bg-clair-4'}`}
                      onClick={() => onSelectError?.(bucket.service_name, bucket.error_reason)}
                      title={onSelectError ? "Click to filter by this error" : undefined}
                    >
                      <td className="p-3 text-gris-primary">{(currentPage - 1) * PAGE_SIZE + index + 1}</td>
                      <td className="p-3 font-medium text-noir-primary whitespace-nowrap">{bucket.service_name}</td>
                      <td className="p-3 text-noir-primary break-all">{bucket.error_reason}</td>
                      <td className="p-3 text-right font-mono text-noir-primary">{bucket.count.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer with pagination */}
        {!loading && buckets.length > PAGE_SIZE && (
          <div className="border-t border-gris-blanc p-4">
            <Pagination
              currentPage={currentPage}
              totalItems={buckets.length}
              itemsPerPage={PAGE_SIZE}
              onPageChange={setCurrentPage}
            />
          </div>
        )}
      </div>
    </div>
  );
}
