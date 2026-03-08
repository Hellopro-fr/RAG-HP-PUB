"use client"

import * as React from "react";
import { useState } from "react"
import { X, Save } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiCreateRule } from "@/lib/api"

interface CreateRuleModalProps {
  currentSearchTerm: string;
  currentFilters: Record<string, any>;
  onClose: () => void;
}

export default function CreateRuleModal({ currentSearchTerm, currentFilters, onClose }: CreateRuleModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    if (!name.trim()) {
        alert("Please provide a name for this rule.");
        return;
    }
    
    try {
        setIsSaving(true);
        await apiCreateRule({
            name,
            description,
            search_term: currentSearchTerm,
            filters: currentFilters,
            is_active: true
        });
        alert("Auto-Archive Rule created successfully!");
        onClose();
    } catch (error) {
        console.error("Failed to create rule", error);
        alert("Failed to save rule. Check console for details.");
        setIsSaving(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
        <div className="bg-white-primary rounded-lg shadow-lg max-w-lg w-full flex flex-col" onClick={(e) => e.stopPropagation()}>
          
          <div className="border-b border-gris-blanc p-4 sm:p-6 flex justify-between items-start gap-4">
            <div>
              <h2 className="text-lg sm:text-xl font-semibold text-noir-primary">Save Search as Rule</h2>
              <p className="text-xs sm:text-sm text-gris-primary mt-1">
                Incoming messages matching this query will be automatically archived.
              </p>
            </div>
            <button onClick={onClose} className="text-gris-primary hover:text-noir-primary shrink-0">
              <X className="w-5 h-5 sm:w-6 sm:h-6" />
            </button>
          </div>

          <div className="p-4 sm:p-6 space-y-4">
            <div>
                <label className="block text-sm font-medium text-noir-primary mb-1">Rule Name <span className="text-rouge-primary">*</span></label>
                <input 
                    type="text" 
                    value={name} 
                    onChange={e => setName(e.target.value)}
                    placeholder="e.g., Ignore Test Web Products"
                    className="w-full border border-gris-blanc rounded px-3 py-2 text-sm focus:outline-bleu-primary"
                    autoFocus
                />
            </div>
            
            <div>
                <label className="block text-sm font-medium text-noir-primary mb-1">Description (Optional)</label>
                <textarea 
                    value={description} 
                    onChange={e => setDescription(e.target.value)}
                    placeholder="Briefly explain what this rule ignores..."
                    className="w-full border border-gris-blanc rounded px-3 py-2 text-sm focus:outline-bleu-primary h-20 resize-none"
                />
            </div>

            <div className="bg-clair-4 p-3 rounded border border-gris-blanc text-xs font-mono text-gris-primary break-all space-y-2">
                <p><span className="font-semibold text-noir-primary">Search Term:</span> {currentSearchTerm || "(None)"}</p>
                <p><span className="font-semibold text-noir-primary">Filters:</span> {Object.keys(currentFilters).length > 0 ? JSON.stringify(currentFilters) : "(None)"}</p>
            </div>
          </div>

          <div className="border-t border-gris-blanc p-4 sm:p-6 flex justify-end gap-3">
            <Button variant="outline" onClick={onClose} disabled={isSaving}>Cancel</Button>
            <Button 
                onClick={handleSave} 
                disabled={isSaving || !name.trim()}
                style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
            >
                {isSaving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Rule</>}
            </Button>
          </div>

        </div>
      </div>
    </>
  )
}