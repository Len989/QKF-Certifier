private static long computeLowerBound(int bits, long lowerBound, long mustBeSet, long mayBeSet, boolean canBeZero) {
        long newLowerBound = minValueForMasks(bits, mustBeSet, mayBeSet);
        final long optionalBits = mayBeSet & ~mustBeSet & CodeUtil.mask(bits - 1);
        if (newLowerBound < lowerBound) {
            if (optionalBits == 0) {
                newLowerBound = 0;
            } else {
                // First find the largest value which is less than or equal to the current bound
                for (int position = bits - 1; position >= 0; position--) {
                    long bit = 1L << position;
                    if ((bit & optionalBits) != 0) {
                        if (newLowerBound + bit <= lowerBound) {
                            newLowerBound += bit;
                        }
                    }
                }
                GraalError.guarantee(newLowerBound <= lowerBound, "should have been sufficient");
                if (newLowerBound < lowerBound) {
                    // Increment the first optional bit and then adjust the bits upward until it's
                    // compatible with the masks
                    boolean incremented = false;
                    for (int position = 0; position < bits - 1; position++) {
                        long bit = 1L << position;
                        if (incremented) {
                            // We have to propagate any carried bit that changed any bits which must
                            // be set or cleared.
                            if ((bit & mustBeSet) != 0 && (newLowerBound & bit) == 0) {
                                // A mustBeSet bit has been cleared so set it
                                newLowerBound |= bit;
                            }
                            if ((bit & mayBeSet) == 0 && (newLowerBound & bit) != 0) {
                                // A bit has carried into the clear section so it needs to propagate
                                // into an mayBeSet bit.
                                newLowerBound += bit;
                            }
                        } else if ((bit & optionalBits) != 0) {
                            newLowerBound += bit;
                            incremented = true;
                        }
                    }
                }
            }
        }
        if (newLowerBound == 0 && !canBeZero) {
            // The actual upper bound must positive
            if (mustBeSet > 0) {
                newLowerBound = mustBeSet;
            } else if (mustBeSet == 0) {
                int lowBit = Long.numberOfTrailingZeros(mayBeSet);
                newLowerBound = 1L << lowBit;
            } else {
                // There is no positive value which is compatible with the masks to return the max
                // value.
                newLowerBound = CodeUtil.maxValue(bits);
            }
        }
        if (newLowerBound < lowerBound) {
            // There is no lower bound which is greater than or equal to the current bound
            // so return the max value.
            return CodeUtil.maxValue(bits);
        }
        return newLowerBound;
    }
