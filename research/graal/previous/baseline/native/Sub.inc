protected Stamp foldStampImpl(Stamp a, Stamp b) {
                            return OPS.getAdd().foldStamp(a, OPS.getNeg().foldStamp(b));
                        }
