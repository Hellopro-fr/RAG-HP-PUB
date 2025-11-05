import React from 'react';

function Pagination({ currentPage, totalPages, onPageChange }) {
    const handlePrevious = () => {
        if (currentPage > 1) {
            onPageChange(currentPage - 1);
        }
    };

    const handleNext = () => {
        if (currentPage < totalPages) {
            onPageChange(currentPage + 1);
        }
    };

    if (totalPages <= 1) {
        return null;
    }

    return (
        <div className="flex items-center justify-between text-sm">
            <button
                onClick={handlePrevious}
                disabled={currentPage === 1}
                className="px-3 py-1 bg-white-primary border border-gris-blanc text-noir-primary rounded-md disabled:opacity-50 disabled:cursor-not-allowed hover:bg-clair-3"
            >
                Previous
            </button>
            <span className="text-gris-primary">
                Page {currentPage} of {totalPages}
            </span>
            <button
                onClick={handleNext}
                disabled={currentPage === totalPages}
                className="px-3 py-1 bg-white-primary border border-gris-blanc text-noir-primary rounded-md disabled:opacity-50 disabled:cursor-not-allowed hover:bg-clair-3"
            >
                Next
            </button>
        </div>
    );
}

export default Pagination;