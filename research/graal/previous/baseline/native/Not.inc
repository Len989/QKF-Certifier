protected Stamp foldStampImpl(Stamp stamp) {
                            if (stamp.isEmpty()) {
                                return stamp;
                            }
                            IntegerStamp integerStamp = (IntegerStamp) stamp;
                            int bits = integerStamp.getBits();
                            long defaultMask = CodeUtil.mask(bits);
                            long lowerBoundInput = ~integerStamp.upperBound();
                            long upperBoundInput = ~integerStamp.lowerBound();
                            long mustBeSet1 = (~integerStamp.mayBeSet()) & defaultMask;
                            long mayBeSet1 = (~integerStamp.mustBeSet()) & defaultMask;
                            return IntegerStamp.create(bits, lowerBoundInput, upperBoundInput, mustBeSet1, mayBeSet1);
                        }
