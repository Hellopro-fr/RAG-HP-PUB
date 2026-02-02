"use client";

import { X, Clock, ChevronLeft, ChevronRight, Check, Trash2, HelpCircle, Truck, Play, Building2, ZoomIn, ChevronDown, ChevronUp } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { trackProductModalView } from "@/lib/analytics";
import type { ProductSpec, SupplierInfo, MediaItem } from "@/types";

interface ProductDetailProps {
  product: {
    id: string;
    name: string;
    images: string[];
    media?: MediaItem[];
    description: string;
    descriptionHtml?: string;
    specs: ProductSpec[];
    supplier: SupplierInfo;
    matchScore: number;
    matchReasons?: string[];
  };
  onClose: () => void;
  onSelect: () => void;
  isSelected: boolean;
}

// Helper to extract YouTube video ID
const getYouTubeId = (url: string): string | null => {
  const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
  const match = url.match(regExp);
  return match && match[2].length === 11 ? match[2] : null;
};

// Helper to get YouTube thumbnail
const getYouTubeThumbnail = (videoId: string): string => {
  return `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
};

const ProductDetailModal = ({ product, onClose, onSelect, isSelected }: ProductDetailProps) => {
  const [currentMediaIndex, setCurrentMediaIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [descriptionExpanded, setDescriptionExpanded] = useState(false);
  const [isDescriptionTruncated, setIsDescriptionTruncated] = useState(false);
  const descriptionRef = useRef<HTMLDivElement>(null);

  // Track modal view on mount + Check if description is truncated
  useEffect(() => {
    // Track product modal view (only once per product per session)
    trackProductModalView(product.id, product.name, product.supplier.name);

    if (descriptionRef.current) {
      const element = descriptionRef.current;
      setIsDescriptionTruncated(element.scrollHeight > element.clientHeight);
    }
  }, [product.id, product.name, product.supplier.name, product.descriptionHtml, product.description]);

  // Build media array from images or media prop
  const mediaItems: MediaItem[] = product.media || product.images.map(url => ({ type: "image" as const, url }));

  const nextMedia = () => {
    setCurrentMediaIndex((prev) => (prev + 1) % mediaItems.length);
  };

  const prevMedia = () => {
    setCurrentMediaIndex((prev) => (prev - 1 + mediaItems.length) % mediaItems.length);
  };

  const getMatchColor = () => {
    if (product.matchScore >= 80) return "text-match-high";
    if (product.matchScore >= 60) return "text-match-medium";
    return "text-match-low";
  };

  const currentMedia = mediaItems[currentMediaIndex];
  const isVideo = currentMedia?.type === "video";
  const youtubeId = isVideo ? getYouTubeId(currentMedia.url) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-6 lg:p-8">
      <div className="relative max-h-[95vh] sm:max-h-[95vh] h-full sm:h-auto w-full max-w-5xl overflow-hidden rounded-t-2xl sm:rounded-2xl bg-background shadow-2xl animate-scale-in flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3 sm:px-6 sm:py-4 flex-shrink-0">
          <h2 className="text-lg sm:text-xl lg:text-2xl font-semibold text-foreground pr-8">{product.name}</h2>
          <button
            onClick={onClose}
            className="absolute right-3 top-3 sm:right-4 sm:top-4 rounded-full p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors z-10"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Full-width Media Carousel */}
          <div className="relative w-full aspect-[16/9] sm:aspect-[2/1] bg-muted">
            {isVideo && youtubeId ? (
              <iframe
                src={`https://www.youtube.com/embed/${youtubeId}?rel=0`}
                title="Product video"
                className="absolute inset-0 w-full h-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <button
                onClick={() => setLightboxOpen(true)}
                className="w-full h-full relative group cursor-zoom-in"
              >
                <img
                  src={currentMedia?.url}
                  alt={product.name}
                  className="w-full h-full object-contain bg-muted"
                />
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity bg-background/90 rounded-full p-3 shadow-lg">
                    <ZoomIn className="h-5 w-5 text-foreground" />
                  </div>
                </div>
              </button>
            )}

            {/* Navigation arrows */}
            {mediaItems.length > 1 && (
              <>
                <button
                  onClick={prevMedia}
                  className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-background/90 p-2.5 shadow-lg hover:bg-background transition-colors"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  onClick={nextMedia}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-background/90 p-2.5 shadow-lg hover:bg-background transition-colors"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </>
            )}

            {/* Media indicators */}
            {mediaItems.length > 1 && (
              <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 gap-2">
                {mediaItems.map((_, idx) => (
                  <button
                    key={idx}
                    onClick={() => setCurrentMediaIndex(idx)}
                    className={cn(
                      "h-2.5 rounded-full transition-all",
                      idx === currentMediaIndex
                        ? "bg-primary w-6"
                        : "bg-background/70 w-2.5 hover:bg-background"
                    )}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Thumbnails strip */}
          {mediaItems.length > 1 && (
            <div className="flex gap-2 p-4 overflow-x-auto bg-muted/30 border-b">
              {mediaItems.map((media, idx) => {
                const isMediaVideo = media.type === "video";
                const thumbYoutubeId = isMediaVideo ? getYouTubeId(media.url) : null;
                const thumbnailUrl = isMediaVideo && thumbYoutubeId
                  ? getYouTubeThumbnail(thumbYoutubeId)
                  : media.thumbnail || media.url;

                return (
                  <button
                    key={idx}
                    onClick={() => setCurrentMediaIndex(idx)}
                    className={cn(
                      "relative h-16 w-24 shrink-0 overflow-hidden rounded-lg border-2 transition-all",
                      idx === currentMediaIndex
                        ? "border-primary ring-2 ring-primary/20"
                        : "border-transparent hover:border-primary/50"
                    )}
                  >
                    <img
                      src={thumbnailUrl}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                    {isMediaVideo && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                        <div className="rounded-full bg-white/90 p-1.5">
                          <Play className="h-3 w-3 text-foreground fill-foreground" />
                        </div>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* Product Info */}
          <div className="p-4 sm:p-6 space-y-6">
            {/* Match Score */}
            <div className="rounded-xl border bg-muted/30 p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-muted-foreground">Correspondance avec vos critères</span>
                <span className={cn("text-2xl font-bold", getMatchColor())}>
                  {product.matchScore}%
                </span>
              </div>
            </div>

            {/* Description - Rich HTML support with expandable */}
            <div>
              <h3 className="text-sm font-semibold text-foreground uppercase tracking-wide mb-3">Description</h3>
              <div className="relative">
                {product.descriptionHtml ? (
                  <div
                    ref={descriptionRef}
                    className={cn(
                      "text-sm text-muted-foreground leading-relaxed prose prose-sm max-w-none",
                      "prose-strong:text-foreground prose-strong:font-semibold",
                      "prose-ul:list-disc prose-ul:pl-4 prose-ul:space-y-1",
                      "prose-li:text-muted-foreground",
                      !descriptionExpanded && "max-h-[12rem] overflow-hidden"
                    )}
                    dangerouslySetInnerHTML={{ __html: product.descriptionHtml }}
                  />
                ) : (
                  <div
                    ref={descriptionRef}
                    className={cn(
                      "text-sm text-muted-foreground leading-relaxed",
                      !descriptionExpanded && "max-h-[12rem] overflow-hidden"
                    )}
                  >
                    <p>{product.description}</p>
                  </div>
                )}

                {/* Gradient overlay when truncated */}
                {!descriptionExpanded && isDescriptionTruncated && (
                  <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-background to-transparent pointer-events-none" />
                )}
              </div>

              {/* Show more/less button */}
              {isDescriptionTruncated && (
                <button
                  onClick={() => setDescriptionExpanded(!descriptionExpanded)}
                  className="mt-2 flex items-center gap-1 text-sm font-medium text-primary hover:text-primary/80 transition-colors"
                >
                  {descriptionExpanded ? (
                    <>
                      <ChevronUp className="h-4 w-4" />
                      Voir moins
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-4 w-4" />
                      Voir plus
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Specifications */}
            <div>
              <h3 className="text-sm font-semibold text-foreground uppercase tracking-wide mb-3">Caractéristiques</h3>

              {/* Legend */}
              <div className="flex flex-wrap gap-3 mb-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                  <Check className="h-3.5 w-3.5 text-match-high" />
                  <span>Correspond</span>
                </div>
                <div className="flex items-center gap-1">
                  <X className="h-3.5 w-3.5 text-warning" />
                  <span>Écart</span>
                </div>
                <div className="flex items-center gap-1">
                  <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>Non renseigné</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="h-3.5 w-3.5 rounded-full border-2 border-muted-foreground/50" />
                  <span>Info complémentaire</span>
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                {product.specs
                  .filter(spec => spec.value || spec.matches === undefined)
                  .map((spec, idx) => {
                    const isRequested = spec.isRequested !== false;
                    const isUnknown = spec.matches === undefined || spec.matches === null;
                    const isKO = spec.matches === false;
                    const isOK = spec.matches === true;
                    const isExtraInfo = !isRequested && !isUnknown;

                    // Determine background and styling
                    let bgClass = "bg-muted/50";
                    let borderClass = "";

                    if (isKO) {
                      bgClass = "bg-warning/10";
                      borderClass = "border-l-4 border-l-warning";
                    } else if (isUnknown && isRequested) {
                      bgClass = "bg-muted";
                      borderClass = "border-l-4 border-l-muted-foreground/50";
                    } else if (isOK && isRequested) {
                      bgClass = "bg-match-high/10";
                      borderClass = "border-l-4 border-l-match-high";
                    } else if (isExtraInfo) {
                      bgClass = "bg-muted/30";
                      borderClass = "border-l-4 border-l-transparent";
                    }

                    return (
                      <div
                        key={idx}
                        className={cn(
                          "flex items-start justify-between rounded-lg px-3 py-2.5 text-sm gap-2",
                          bgClass,
                          borderClass
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0 shrink-0">
                          {/* Status icon */}
                          {isKO && <X className="h-4 w-4 text-warning shrink-0" />}
                          {isOK && isRequested && <Check className="h-4 w-4 text-match-high shrink-0" />}
                          {isUnknown && isRequested && <HelpCircle className="h-4 w-4 text-muted-foreground shrink-0" />}
                          {isExtraInfo && <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/40 shrink-0" />}

                          <span className="text-muted-foreground">{spec.label}</span>
                        </div>

                        <div className="flex flex-col items-end text-right">
                          {isUnknown ? (
                            <span className="font-medium text-muted-foreground italic">
                              Non renseigné
                            </span>
                          ) : (
                            <>
                              <span className={cn(
                                "font-medium",
                                isKO ? "text-warning" : isExtraInfo ? "text-muted-foreground" : "text-foreground"
                              )}>
                                {spec.value}
                              </span>
                              {isKO && spec.expected && (
                                <span className="text-xs text-muted-foreground mt-0.5">
                                  Critère demandé : {spec.expected}
                                </span>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>

          {/* Supplier Info */}
          <div className="p-4 sm:p-6 pt-0">
            <h3 className="text-sm font-semibold text-foreground uppercase tracking-wide mb-4">À propos du fournisseur</h3>

            <div className="rounded-xl border bg-card p-4 sm:p-5">
              <div className="flex items-start gap-4">
                {/* Logo or fallback icon */}
                {product.supplier.logo ? (
                  <div className="h-12 w-20 sm:h-14 sm:w-24 shrink-0 overflow-hidden rounded-lg bg-white border flex items-center justify-center p-2">
                    <img
                      src={product.supplier.logo}
                      alt={product.supplier.name}
                      className="max-h-full max-w-full object-contain"
                    />
                  </div>
                ) : (
                  <div className="flex h-12 w-12 sm:h-14 sm:w-14 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                    <Building2 className="h-6 w-6 sm:h-7 sm:w-7 text-primary" />
                  </div>
                )}

                <div className="flex-1 min-w-0">
                  <h4 className="text-base sm:text-lg font-semibold text-foreground">
                    {product.supplier.name}
                  </h4>

                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1 text-match-high">
                      <Truck className="h-4 w-4" />
                      Livre dans votre zone
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-4 w-4" />
                      Répond en {product.supplier.responseTime}
                    </span>
                  </div>
                </div>
              </div>

              <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
                {product.supplier.description}
              </p>
            </div>
          </div>
        </div>

        {/* Footer - Fixed at bottom on mobile */}
        <div className="border-t bg-background p-4 pb-6 sm:pb-4 flex-shrink-0 safe-area-inset-bottom">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sm:gap-4">
            <button
              onClick={onClose}
              className="hidden sm:block text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              ← Retour à la liste
            </button>

            {isSelected ? (
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3 w-full sm:w-auto">
                {/* Selected state badge */}
                <div className="flex items-center justify-center gap-2 rounded-full bg-match-high/15 border border-match-high/30 px-4 py-2">
                  <div className="flex items-center justify-center h-5 w-5 rounded-full bg-match-high">
                    <Check className="h-3 w-3 text-white" />
                  </div>
                  <span className="text-sm font-semibold text-match-high">Produit sélectionné</span>
                </div>

                {/* Remove button - clearly destructive */}
                <Button
                  variant="outline"
                  onClick={() => {
                    onSelect();
                  }}
                  className="gap-2 border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50"
                >
                  <Trash2 className="h-4 w-4" />
                  Retirer de la sélection
                </Button>
              </div>
            ) : (
              <Button
                onClick={() => {
                  onSelect();
                  onClose();
                }}
                className="w-full sm:w-auto px-6 bg-accent hover:bg-accent/90 text-accent-foreground"
              >
                Ajouter à ma sélection
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Lightbox for fullscreen image */}
      {lightboxOpen && !isVideo && (
        <div
          className="fixed inset-0 z-[60] bg-black/95 flex items-center justify-center p-4"
          onClick={() => setLightboxOpen(false)}
        >
          <button
            onClick={() => setLightboxOpen(false)}
            className="absolute top-4 right-4 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 transition-colors z-10"
          >
            <X className="h-6 w-6" />
          </button>

          {/* Navigation in lightbox */}
          {mediaItems.filter(m => m.type === "image").length > 1 && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  prevMedia();
                }}
                className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 transition-colors"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  nextMedia();
                }}
                className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 transition-colors"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            </>
          )}

          <img
            src={currentMedia?.url}
            alt={product.name}
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
};

export default ProductDetailModal;
