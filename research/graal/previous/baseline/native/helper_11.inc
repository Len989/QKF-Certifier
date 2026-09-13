private static long minValueForMasks(int bits, long mustBeSet, long mayBeSet) {
        if (significantBit(bits, mayBeSet) == 0) {
            // Value is always positive. Minimum value always positive.
            assert significantBit(bits, mustBeSet) == 0 : String.format("must: %016x may: %016x", mustBeSet, mayBeSet);
            return mustBeSet;
        } else {
            // Value can be positive or negative. Minimum value always negative.
            return mustBeSet | (-1L << (bits - 1));
        }
    }
