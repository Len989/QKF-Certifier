private static boolean isEmpty(long lowerBound, long upperBound, long mustBeSet, long mayBeSet) {
        return lowerBound > upperBound || (mustBeSet & (~mayBeSet)) != 0 || (mayBeSet == 0 && (lowerBound > 0 || upperBound < 0));
    }
