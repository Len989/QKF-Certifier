private static long computeUpperBound(int bits, long upperBound, long mustBeSet, long mayBeSet, boolean canBeZero) {
        // Start with the sign extended mustBeSet. That will be the smallest positive or negative
        // value.
        long newUpperBound = CodeUtil.signExtend(mustBeSet, bits);
        if (upperBound < 0 || newUpperBound > upperBound) {
            // If the upper bound is negative or it's positive but greater than the least
            // positive value, then start from the minimum negative value
            newUpperBound = minValueForMasks(bits, mustBeSet, mayBeSet);
        }
        // Compute the bits which are set in the mayBeSet but not the mustBeSet, ignoring the sign
        // bit which was handled above.
        newUpperBound = setOptionalBits(bits, upperBound, mustBeSet, mayBeSet, newUpperBound);

        if (newUpperBound == 0 && !canBeZero) {
            // The actual upper bound must be negative
            if (significantBit(bits, mayBeSet) == 0) {
                // All values are positive so return the minimum value.
                return CodeUtil.minValue(bits);
            } else {
                // Choose the max negative value
                newUpperBound = maxValueForMasks(bits, mustBeSet | (1L << bits - 1), mayBeSet);
            }
        }

        if (newUpperBound > upperBound) {
            // The smallest upper bound that's compatible with the masks is larger than the expected
            // upper bound, so return the minimum value.
            return CodeUtil.minValue(bits);
        }
        return newUpperBound;
    }
