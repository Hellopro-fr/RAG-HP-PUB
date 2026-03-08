"use client"

import * as React from "react";
import { useState, useEffect } from "react"
import { apiGetRules, apiToggleRule, apiDeleteRule, AutoArchiveRule } from "@/lib/api"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { Trash2, AlertCircle } from "lucide-react"

export default function RulesPage() {
    const [rules, setRules] = useState<AutoArchiveRule[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchRules = async () => {
        try {
            setLoading(true);
            const res = await apiGetRules();
            setRules(res.data);
        } catch (error) {
            console.error("Failed to load rules", error);
            alert("Failed to load rules.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRules();
    }, []);

    const handleToggle = async (ruleId: string, currentStatus: boolean) => {
        try {
            // Optimistic update
            setRules(rules.map(r => r._id === ruleId ? { ...r, is_active: !currentStatus } : r));
            await apiToggleRule(ruleId, !currentStatus);
        } catch (error) {
            alert("Failed to update rule status.");
            fetchRules(); // Revert on failure
        }
    };

    const handleDelete = async (ruleId: string) => {
        if (!window.confirm("Are you sure you want to permanently delete this rule?")) return;
        try {
            await apiDeleteRule(ruleId);
            setRules(rules.filter(r => r._id !== ruleId));
        } catch (error) {
            alert("Failed to delete rule.");
        }
    };

    if (loading) return <div className="p-8 text-center text-gris-primary">Loading rules...</div>;

    return (
        <div className="p-4 md:p-8 space-y-6">
            <div className="bg-bleu-light border border-bleu-primary/20 p-4 rounded-lg flex gap-3 text-sm text-noir-primary">
                <AlertCircle className="w-5 h-5 text-bleu-primary shrink-0" />
                <p>
                    Auto-Archive Rules automatically move <strong>"New"</strong> messages matching specific queries to the 
                    <span className="font-semibold text-gris-primary bg-clair-4 px-2 py-0.5 rounded mx-1">Auto-Archived</span> 
                    status. The background engine checks for new matches every minute.
                </p>
            </div>

            {rules.length === 0 ? (
                <div className="text-center p-8 border border-dashed border-gris-blanc rounded-lg bg-white-primary">
                    <p className="text-gris-primary">No rules configured yet.</p>
                    <p className="text-sm mt-2 text-noir-primary">You can create a rule directly from the "Search & Re-queue" page.</p>
                </div>
            ) : (
                <div className="bg-white-primary rounded-lg border border-gris-blanc overflow-x-auto w-full">
                    <table className="w-full min-w-[800px]">
                        <thead>
                            <tr className="border-b border-gris-blanc bg-clair-4">
                                <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary w-1/4">Rule Name & Description</th>
                                <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary w-2/5">Target Conditions</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Executions</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Active</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rules.map((rule) => (
                                <tr key={rule._id} className="border-b border-gris-blanc hover:bg-clair-4 transition-colors">
                                    <td className="px-6 py-4">
                                        <p className="font-semibold text-noir-primary text-sm">{rule.name}</p>
                                        {rule.description && (
                                            <p className="text-xs text-gris-primary mt-1 line-clamp-2" title={rule.description}>{rule.description}</p>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-xs font-mono text-gris-primary break-all">
                                        {rule.search_term && <div><span className="font-semibold text-noir-primary">Query:</span> {rule.search_term}</div>}
                                        {rule.filters && Object.keys(rule.filters).length > 0 && (
                                            <div className="mt-1"><span className="font-semibold text-noir-primary">Filters:</span> {JSON.stringify(rule.filters)}</div>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-center text-sm font-medium text-bleu-primary">
                                        {rule.execution_count?.toLocaleString() || 0}
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <Switch 
                                            checked={rule.is_active} 
                                            onCheckedChange={() => handleToggle(rule._id!, rule.is_active)} 
                                        />
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => handleDelete(rule._id!)}
                                            className="text-rouge-primary hover:bg-rouge-light hover:text-rouge-primary"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}