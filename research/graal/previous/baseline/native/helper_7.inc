public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput, long mustBeSet, long mayBeSet) {
        return create(bits, lowerBoundInput, upperBoundInput, mustBeSet, mayBeSet, true);
    }
